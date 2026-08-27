"""reminders.py: turn an LLM-extracted {text, datetime} dict into a Windows
toast, now or later.

This never touches a real winotify Notification or a real background timer —
`_fire_toast` and `threading.Timer` are mocked in every test, so running this
suite pops no toast on the machine it runs on. What's under test is the
routing logic: does a given datetime fire immediately or get scheduled, and
is the delay computed correctly? The four states are kept apart on
purpose: `future` schedules, `past` fires now, and `absent`/`unparseable`
do neither -- see the reminders.py docstring for why silence is correct
there.
"""
import pytest

import reminders


class _RefusingTimer:
    """Used where a test wants to prove threading.Timer is never touched."""

    def __init__(self, *a, **kw):
        raise AssertionError("threading.Timer should not be used for this case")


class _FakeTimer:
    instances = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.started = False
        type(self).instances.append(self)

    def start(self):
        self.started = True


@pytest.fixture
def fake_timer(monkeypatch):
    _FakeTimer.instances = []
    monkeypatch.setattr(reminders.threading, "Timer", _FakeTimer)
    return _FakeTimer


@pytest.fixture
def fire_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(reminders, "_fire_toast", lambda **kw: calls.append(kw))
    return calls


# -- unschedulable: neither fired nor scheduled ------------------------------

def test_no_datetime_neither_fires_nor_schedules(monkeypatch, fire_spy):
    """The eval's `short-transcript-01` ("Buy milk."): a real reminder with no
    time on it. It used to toast the instant the note saved."""
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    out = reminders._schedule_one({"text": "check the oven", "datetime": ""}, "Kitchen note")

    assert fire_spy == [], "an undated reminder must not interrupt"
    assert out["state"] == reminders.ABSENT


def test_an_unparsable_datetime_neither_fires_nor_schedules(monkeypatch, fire_spy):
    """'tomorrow morning' and 'in two weeks' are what the model actually emits,
    and dateutil resolves neither."""
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    out = reminders._schedule_one({"text": "garbled", "datetime": "not a date at all"}, "Note")

    assert fire_spy == []
    assert out["state"] == reminders.UNPARSEABLE


# -- immediate-fire routing --------------------------------------------------

def test_a_past_datetime_fires_immediately(monkeypatch, fire_spy):
    """A moment that has genuinely passed is a heads-up worth showing. The
    hallucinated-year case that made this fire wrongly is fixed in the prompt,
    not here -- see evals/README.md."""
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    out = reminders._schedule_one(
        {"text": "old task", "datetime": "2020-01-01T00:00:00+00:00"}, "Old note"
    )

    assert len(fire_spy) == 1
    assert fire_spy[0]["text"] == "old task"
    assert out["state"] == reminders.FIRED


# -- deferred-fire routing ---------------------------------------------------

def test_a_future_datetime_schedules_a_timer_instead_of_firing_now(fake_timer, fire_spy):
    reminder = {"text": "future task", "datetime": "2099-01-01T00:00:00+00:00"}
    reminders._schedule_one(reminder, "Future note")

    assert fire_spy == [], "should not fire synchronously"
    assert len(fake_timer.instances) == 1
    scheduled = fake_timer.instances[0]
    assert scheduled.interval > 0
    assert scheduled.started is True


def test_a_naive_future_datetime_is_treated_as_utc_and_still_schedules(fake_timer, fire_spy):
    """dateutil returns a naive datetime for e.g. 'next Monday 9am'; reminders.py
    assumes UTC for it rather than crashing on the aware/naive comparison."""
    reminder = {"text": "naive future task", "datetime": "January 1, 2099 9:00am"}
    reminders._schedule_one(reminder, "Future note")

    assert len(fake_timer.instances) == 1
    assert fake_timer.instances[0].interval > 0


def test_schedule_reminders_returns_a_state_for_every_reminder(monkeypatch, fire_spy):
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    out = reminders.schedule_reminders(
        [
            {"text": "first", "datetime": ""},
            {"text": "second", "datetime": "2020-01-01T00:00:00+00:00"},
        ],
        "Batch note",
    )

    assert [r["text"] for r in out] == ["first", "second"]
    assert [r["state"] for r in out] == [reminders.ABSENT, reminders.FIRED]
    # only the genuinely-past one interrupted
    assert [c["text"] for c in fire_spy] == ["second"]


# -- _fire_toast itself: mock winotify, never show a real toast -------------

def test_fire_toast_truncates_the_message_to_two_hundred_chars(monkeypatch):
    calls = {}

    class FakeNotification:
        def __init__(self, app_id, title, msg, duration):
            calls["app_id"] = app_id
            calls["title"] = title
            calls["msg"] = msg

        def set_audio(self, audio_value, loop):
            pass

        def show(self):
            calls["shown"] = True

    monkeypatch.setattr(reminders, "Notification", FakeNotification)
    reminders._fire_toast("A Title", "x" * 300)

    assert len(calls["msg"]) == 200
    assert calls["shown"] is True
    assert calls["app_id"] == "VoiceNote"
