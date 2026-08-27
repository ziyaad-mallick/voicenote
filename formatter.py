"""
Sends raw transcript to Ollama (local LLM) and gets back a structured note.

Returns a dict:
    {
        "title": str,
        "category": str,           # one of the configured categories
        "summary": str,            # 1-2 sentence TL;DR
        "body": str,               # formatted markdown body
        "tags": list[str],
        "reminders": [             # list may be empty
            {"text": str, "datetime": str}  # ISO-8601 or human-readable
        ]
    }
"""

import json
import re
from datetime import datetime

import requests


_SYSTEM = """\
You are a smart note-taking assistant. Given a raw voice transcript, produce a
structured note in JSON with these exact keys:
- title: short, descriptive title (≤60 chars)
- category: one of {categories} — pick the best fit
- summary: 1-2 sentence TL;DR
- body: the note content formatted as clean Markdown (use headings, bullets,
  code blocks where appropriate). Expand shorthand, fix grammar, keep ideas intact.
- tags: list of 3-6 lowercase keyword strings
- reminders: list of objects with "text" (what to do) and "datetime".
  Only include if the transcript explicitly mentions a date, deadline, or
  task. Otherwise empty list.

The current date and time is {now}. Resolve every relative expression
("tomorrow", "next Monday", "in two weeks", "Friday the 5th") against it.

"datetime" MUST be an absolute ISO-8601 timestamp with an explicit year and
UTC offset, for example "2026-09-05T09:00:00+05:00". Never reply with prose
like "next Monday 9am" -- the scheduler cannot read it, and a reminder it
cannot read is silently dropped. If the transcript names a day but no year,
pick the next occurrence at or after the current date; never a past year. If
it names no time of day, use 09:00. If the transcript truly fixes no moment,
omit the "datetime" key rather than inventing one.

Reply with JSON only, no prose outside the JSON block.\
"""


def format_note(
    transcript: str,
    categories: list[str],
    ollama_host: str = "http://localhost:11434",
    model: str = "goekdenizguelmez/JOSIEFIED-Qwen3:latest",
    now: datetime | None = None,
) -> dict:
    # {now} is substituted HERE and deliberately NOT in evals.harness.prompt_hash,
    # which hashes the template with the placeholder still literal. That keeps the
    # hash stable across runs while still changing when the prompt itself changes.
    # Substituting a live timestamp into the hashed string would re-stale every
    # recording every second, and replay would never score anything again.
    stamp = (now or datetime.now().astimezone()).strftime("%Y-%m-%dT%H:%M:%S%z")
    system = _SYSTEM.replace("{categories}", ", ".join(categories)).replace(
        "{now}", stamp
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Transcript:\n\n{transcript}"},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }

    try:
        resp = requests.post(
            f"{ollama_host}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
    except Exception as e:
        return _fallback(transcript, categories, str(e), kind="transport")

    return _parse(content, transcript, categories)


def _parse(content: str, transcript: str, categories: list[str]) -> dict:
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()
    try:
        data = json.loads(cleaned)
        # Validate required keys exist
        for key in ("title", "category", "summary", "body", "tags", "reminders"):
            if key not in data:
                raise ValueError(f"Missing key: {key}")
        if data["category"] not in categories:
            data["category"] = categories[0]
            # Flagged, not silent: without this, a model returning nonsense
            # scores as a correct `categories[0]` prediction and category
            # accuracy measures the coercion instead of the model.
            data["_category_coerced"] = True
        return data
    except Exception:
        return _fallback(transcript, categories, "parse error", kind="parse")


def _fallback(transcript: str, categories: list[str], reason: str, kind: str) -> dict:
    """Raw transcript, preserved, when the LLM path could not produce a note.

    `kind` is the machine-readable discriminator: "transport" when the request
    never came back, "parse" when it did but the body was not usable. They are
    different failures with different fixes, and `reason` alone cannot separate
    them -- it carries free-form exception text in the transport case.
    """
    return {
        "title": transcript[:60].strip() or "Untitled Note",
        "category": categories[0],
        "summary": transcript[:120],
        "body": transcript,
        "tags": [],
        "reminders": [],
        "_fallback_reason": reason,
        "_fallback_kind": kind,
    }
