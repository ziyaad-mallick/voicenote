"""Run cases through the real formatter, in replay or live mode.

Replay swaps out `formatter.requests.post` -- the one network seam in this
codebase -- for a stub returning a response recorded earlier. Everything else is
the production path: the real prompt interpolation, the real `_parse`, the real
fence-stripping, the real category coercion, the real fallback.

What replay CAN gate: the parser. Fence-stripping, key validation, category
coercion and both fallback paths are deterministic given a response body, so a
regression in any of them shows up as an exact per-case diff.

What replay CANNOT do, and this is the thing to be clear about: evaluate a
prompt change. The recorded response was produced by whatever prompt was in
effect when it was recorded. Replay discards the payload the formatter builds,
so editing `_SYSTEM` moves no metric at all -- a CI gate that did not know this
would green-tick every prompt regression. Hence `prompt_sha`: each recording
stores a hash of the system prompt as sent, and replay refuses to score a case
whose prompt has since changed. A prompt edit becomes a loud STALE, not a
silent pass.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import formatter

from .harness import Case, Metrics, prompt_hash, score


class StaleRecording(Exception):
    """The prompt changed since this case was recorded."""


class _RecordedResponse:
    """Shaped like the slice of `requests.Response` that formatter.py uses."""

    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


def run_case(case: Case, categories: list[str], live: bool, monkeypatch=None) -> dict:
    """Produce a note for one case. Returns the note dict formatter returns."""
    if live:
        return formatter.format_note(case.transcript, categories=categories)

    if not case.recorded:
        raise StaleRecording(
            f"{case.id}: no recorded response. Run `python -m evals.run --live` "
            f"against a running Ollama to record one."
        )

    if case.recorded.get("transport_error"):
        # Simulates Ollama being unreachable. This is a real code path in
        # formatter.py, not a fabricated model response: the point is to assert
        # the fallback fires and the raw transcript survives. No prompt reached a
        # model, so there is no recorded prompt to go stale -- the hash check
        # below deliberately does not apply.
        def _boom(*a, **kw):
            raise ConnectionError(case.recorded["transport_error"])

        return _with_post(_boom, case, categories)

    expected_sha = case.recorded.get("prompt_sha")
    actual_sha = prompt_hash(categories)
    if expected_sha != actual_sha:
        raise StaleRecording(
            f"{case.id}: recorded against prompt {expected_sha}, current prompt is "
            f"{actual_sha}. The recording cannot tell you anything about the current "
            f"prompt's behaviour -- re-record with `python -m evals.run --live`."
        )

    content = case.recorded["response"]
    return _with_post(lambda *a, **kw: _RecordedResponse(content), case, categories)


def _with_post(fake_post, case: Case, categories: list[str]) -> dict:
    original = formatter.requests.post
    formatter.requests.post = fake_post
    try:
        return formatter.format_note(case.transcript, categories=categories)
    finally:
        formatter.requests.post = original


def record_case(case: Case, categories: list[str], timeout: int | None = None) -> dict:
    """Call the real Ollama and capture the raw response body for replay.

    `timeout` overrides `formatter`'s hardcoded 120s for the recording call only.
    Recording is not a measurement of latency -- it is capturing what the model
    says -- and on a thinking model a long transcript can take several minutes to
    generate. Letting the recorder time out would mean the eval simply has no
    case for the inputs the model finds hardest, which is the opposite of what a
    test set is for.

    The 120s limit is itself worth measuring, and is reported separately rather
    than being silently raised: on the machine this was recorded on,
    `rambling-two-topics-01` took 196.7s, so in real use that note falls back to
    the raw transcript.
    """
    payload_sha = prompt_hash(categories)
    captured: dict = {}
    original = formatter.requests.post

    def _capturing_post(*args, **kwargs):
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = original(*args, **kwargs)
        try:
            captured["content"] = resp.json()["message"]["content"]
        except Exception:
            captured["content"] = None
        return resp

    formatter.requests.post = _capturing_post
    try:
        note = formatter.format_note(case.transcript, categories=categories)
    finally:
        formatter.requests.post = original

    if captured.get("content") is None:
        raise RuntimeError(
            f"{case.id}: Ollama did not return a usable body; nothing recorded."
        )
    return {"prompt_sha": payload_sha, "response": captured["content"], "note": note}


def run_all(cases: list[Case], categories: list[str], live: bool = False) -> tuple[Metrics, list[str]]:
    """Score every case. Returns (metrics, stale_case_ids)."""
    metrics = Metrics()
    stale: list[str] = []
    now = datetime.now(tz=timezone.utc)
    for case in cases:
        try:
            note = run_case(case, categories, live=live)
        except StaleRecording as exc:
            stale.append(str(exc))
            continue
        score(case, note, metrics, now=now)
    return metrics, stale
