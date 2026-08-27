"""
Schedules Windows toast notifications for reminders extracted by the LLM.

Each reminder dict has:
    {"text": str, "datetime": str}  # datetime may be ISO-8601 or human-readable

We parse the datetime with dateutil and fire a toast notification via winotify.

A reminder whose time cannot be resolved is NOT fired. Firing it is what the
eval in `evals/` caught: a zero delay was reached three different ways -- no
datetime at all, a datetime dateutil cannot read, and a datetime already past --
and all three fell through the same `delay < 1` branch into an immediate toast.
Five of six correctly-extracted reminders interrupted the user the instant the
note was saved. "I don't know when" is not "now", and only a moment that has
genuinely passed is a heads-up worth interrupting someone for.

Nothing is lost by staying quiet: writer.py records every reminder in the note's
frontmatter and body regardless of what happens here.
"""

from __future__ import annotations
import threading
from datetime import datetime, timezone

from dateutil import parser as dateparser
from winotify import Notification, audio


APP_ID = "VoiceNote"

# States a reminder's datetime can be in. Deliberately the same vocabulary as
# evals/harness.datetime_state, so the metric and the behaviour it measures
# cannot drift apart in name. The harness collapses `past` and `unparseable`
# into one bucket because it is scoring whether the scheduler can use the
# string; here they are separate because they route differently.
SCHEDULED = "future"
FIRED = "past"
ABSENT = "absent"
UNPARSEABLE = "unparseable"


def _fire_toast(title: str, text: str):
    toast = Notification(
        app_id=APP_ID,
        title=title,
        msg=text[:200],
        duration="long",
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()


def _resolve(dt_str: str) -> tuple[str, float]:
    """Classify a reminder's datetime, and say how far off it is when schedulable.

    Returns (state, delay_seconds). Delay is meaningful only for `future`.
    """
    if not dt_str:
        return ABSENT, 0.0

    try:
        dt = dateparser.parse(dt_str, fuzzy=True)
    except Exception:
        return UNPARSEABLE, 0.0
    if dt is None:
        return UNPARSEABLE, 0.0

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (dt - datetime.now(tz=timezone.utc)).total_seconds()
    if delta < 1:
        return FIRED, 0.0
    return SCHEDULED, delta


def schedule_reminders(reminders: list[dict], note_title: str) -> list[dict]:
    """Route every reminder. Returns one {text, state, delay} per input.

    The return value is what lets a caller report what actually happened
    instead of asserting "Reminder set" for one that never was.
    """
    return [_schedule_one(r, note_title) for r in reminders]


def _schedule_one(reminder: dict, note_title: str) -> dict:
    text = reminder.get("text", "Reminder")
    state, delay = _resolve(reminder.get("datetime", ""))

    def _trigger():
        _fire_toast(
            title=f"VoiceNote Reminder: {note_title[:40]}",
            text=text,
        )

    if state == SCHEDULED:
        threading.Timer(delay, _trigger).start()
    elif state == FIRED:
        _trigger()
    # ABSENT and UNPARSEABLE: neither fired nor scheduled, deliberately.

    return {"text": text, "state": state, "delay": delay}
