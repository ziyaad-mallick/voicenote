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
- reminders: list of objects with "text" (what to do) and "datetime" (ISO 8601
  or descriptive like "next Monday 9am"). Only include if the transcript
  explicitly mentions a date, deadline, or task. Otherwise empty list.

Reply with JSON only, no prose outside the JSON block.\
"""


def format_note(
    transcript: str,
    categories: list[str],
    ollama_host: str = "http://localhost:11434",
    model: str = "goekdenizguelmez/JOSIEFIED-Qwen3:latest",
) -> dict:
    system = _SYSTEM.replace("{categories}", ", ".join(categories))
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
        return _fallback(transcript, categories, str(e))

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
        return data
    except Exception:
        return _fallback(transcript, categories, "parse error")


def _fallback(transcript: str, categories: list[str], reason: str) -> dict:
    return {
        "title": transcript[:60].strip() or "Untitled Note",
        "category": categories[0],
        "summary": transcript[:120],
        "body": transcript,
        "tags": [],
        "reminders": [],
        "_fallback_reason": reason,
    }
