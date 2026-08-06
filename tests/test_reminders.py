"""reminders.py: turn an LLM-extracted {text, datetime} dict into a Windows
toast, now or later.

This never touches a real winotify Notification or a real background timer —
`_fire_toast` and `threading.Timer` are mocked in every test, so running this
suite pops no toast on the machine it runs on. What's under test is the
routing logic: does a given datetime fire immediately or get scheduled, and
is the delay computed correctly (past/unparsable -> now, future -> a
positive delay)?
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


# -- immediate-fire routing --------------------------------------------------

def test_no_datetime_fires_immediately_without_scheduling(monkeypatch, fire_spy):
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    reminders._schedule_one({"text": "check the oven", "datetime": ""}, "Kitchen note")

    assert len(fire_spy) == 1
    assert fire_spy[0]["text"] == "check the oven"
    assert "Kitchen note" in fire_spy[0]["title"]


def test_a_past_datetime_fires_immediately(monkeypatch, fire_spy):
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    reminder = {"text": "old task", "datetime": "2020-01-01T00:00:00+00:00"}
    reminders._schedule_one(reminder, "Old note")

    assert len(fire_spy) == 1
    assert fire_spy[0]["text"] == "old task"


def test_an_unparsable_datetime_fires_immediately_as_a_heads_up(monkeypatch, fire_spy):
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    reminder = {"text": "garbled", "datetime": "not a date at all"}
    reminders._schedule_one(reminder, "Note")

    assert len(fire_spy) == 1
    assert fire_spy[0]["text"] == "garbled"


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


def test_schedule_reminders_processes_every_reminder_in_the_list(monkeypatch, fire_spy):
    monkeypatch.setattr(reminders.threading, "Timer", _RefusingTimer)
    reminders.schedule_reminders(
        [
            {"text": "first", "datetime": ""},
            {"text": "second", "datetime": ""},
        ],
        "Batch note",
    )
    assert [c["text"] for c in fire_spy] == ["first", "second"]


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
