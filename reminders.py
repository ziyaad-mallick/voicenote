"""
Schedules Windows toast notifications for reminders extracted by the LLM.

Each reminder dict has:
    {"text": str, "datetime": str}  # datetime may be ISO-8601 or human-readable

We parse the datetime with dateutil and fire a toast notification via winotify.
If datetime is in the past or unparsable, we fire immediately as a heads-up.
"""

from __future__ import annotations
import threading
from datetime import datetime, timezone

from dateutil import parser as dateparser
from winotify import Notification, audio


APP_ID = "VoiceNote"


def _fire_toast(title: str, text: str):
    toast = Notification(
        app_id=APP_ID,
        title=title,
        msg=text[:200],
        duration="long",
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()


def schedule_reminders(reminders: list[dict], note_title: str):
    for r in reminders:
        _schedule_one(r, note_title)


def _schedule_one(reminder: dict, note_title: str):
    text = reminder.get("text", "Reminder")
    dt_str = reminder.get("datetime", "")
    delay = 0.0

    if dt_str:
        try:
            dt = dateparser.parse(dt_str, fuzzy=True)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                now = datetime.now(tz=timezone.utc)
                delta = (dt - now).total_seconds()
                delay = max(0.0, delta)
        except Exception:
            pass

    def _trigger():
        _fire_toast(
            title=f"VoiceNote Reminder: {note_title[:40]}",
            text=text,
        )

    if delay < 1:
        _trigger()
    else:
        threading.Timer(delay, _trigger).start()
