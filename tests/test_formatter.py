"""formatter.py: send a transcript to Ollama, get back a structured note.

The one promise this module makes publicly is graceful degradation — if
Ollama is unreachable or answers with garbage, the note still gets written:
a `_fallback_reason` is set and the raw transcript survives as the body.
Losing a thought because a daemon was down is the one unacceptable failure
for a note-taking tool, so that path is tested first and hardest.

requests.post is mocked at the HTTP boundary in every test — nothing here
touches a real network or a real Ollama instance.
"""
import requests
import pytest

import formatter


CATEGORIES = ["Projects", "Ideas", "Uni", "Personal"]


class _FakeResponse:
    def __init__(self, content=None, status_code=200):
        self._content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return {"message": {"content": self._content}}


VALID_CONTENT = """{
    "title": "Buy groceries",
    "category": "Personal",
    "summary": "Need to buy milk and eggs.",
    "body": "Buy milk and eggs from the store.",
    "tags": ["groceries", "errand"],
    "reminders": []
}"""


# -- graceful degradation --------------------------------------------------

def test_connection_error_falls_back_and_keeps_the_raw_transcript(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("Ollama not running")

    monkeypatch.setattr(formatter.requests, "post", boom)
    note = formatter.format_note("remember to call mum tomorrow", CATEGORIES)

    assert "_fallback_reason" in note
    assert note["body"] == "remember to call mum tomorrow"
    assert note["reminders"] == []


def test_fallback_reason_names_the_underlying_error(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("Ollama not running")

    monkeypatch.setattr(formatter.requests, "post", boom)
    note = formatter.format_note("hello", CATEGORIES)

    assert "Ollama not running" in note["_fallback_reason"]


def test_http_error_status_falls_back(monkeypatch):
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse(status_code=500)
    )
    note = formatter.format_note("some transcript", CATEGORIES)

    assert "_fallback_reason" in note
    assert note["body"] == "some transcript"


def test_timeout_falls_back(monkeypatch):
    def boom(*a, **kw):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(formatter.requests, "post", boom)
    note = formatter.format_note("a slow thought", CATEGORIES)

    assert "_fallback_reason" in note
    assert note["body"] == "a slow thought"


def test_malformed_json_falls_back_with_parse_error_reason(monkeypatch):
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse("not json at all")
    )
    note = formatter.format_note("a transcript", CATEGORIES)

    assert note["_fallback_reason"] == "parse error"
    assert note["body"] == "a transcript"


def test_json_missing_a_required_key_falls_back(monkeypatch):
    incomplete = '{"title": "x", "category": "Personal"}'
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse(incomplete)
    )
    note = formatter.format_note("a transcript", CATEGORIES)

    assert note["_fallback_reason"] == "parse error"


def test_fallback_title_is_truncated_to_sixty_chars(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(formatter.requests, "post", boom)
    long_transcript = "x" * 200
    note = formatter.format_note(long_transcript, CATEGORIES)

    assert len(note["title"]) == 60


def test_empty_transcript_gets_a_placeholder_title_on_fallback(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(formatter.requests, "post", boom)
    note = formatter.format_note("   ", CATEGORIES)

    assert note["title"] == "Untitled Note"


def test_fallback_uses_the_first_configured_category(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(formatter.requests, "post", boom)
    note = formatter.format_note("a transcript", CATEGORIES)

    assert note["category"] == CATEGORIES[0]


# -- the happy path (and near-happy path) ----------------------------------

def test_valid_response_is_parsed_and_returned(monkeypatch):
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse(VALID_CONTENT)
    )
    note = formatter.format_note("buy milk and eggs", CATEGORIES)

    assert "_fallback_reason" not in note
    assert note["title"] == "Buy groceries"
    assert note["category"] == "Personal"
    assert note["tags"] == ["groceries", "errand"]


def test_json_wrapped_in_a_markdown_code_fence_is_still_parsed(monkeypatch):
    fenced = "```json\n" + VALID_CONTENT + "\n```"
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse(fenced)
    )
    note = formatter.format_note("buy milk and eggs", CATEGORIES)

    assert "_fallback_reason" not in note
    assert note["title"] == "Buy groceries"


def test_a_category_outside_the_configured_list_is_coerced_to_the_first_one(monkeypatch):
    off_list = VALID_CONTENT.replace('"Personal"', '"NotARealCategory"')
    monkeypatch.setattr(
        formatter.requests, "post", lambda *a, **kw: _FakeResponse(off_list)
    )
    note = formatter.format_note("buy milk and eggs", CATEGORIES)

    assert note["category"] == CATEGORIES[0]


def test_categories_are_interpolated_into_the_system_prompt(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        return _FakeResponse(VALID_CONTENT)

    monkeypatch.setattr(formatter.requests, "post", fake_post)
    formatter.format_note("buy milk and eggs", CATEGORIES)

    for category in CATEGORIES:
        assert category in captured["system"]
