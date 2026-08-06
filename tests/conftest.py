"""Shared test fixtures.

Nothing in this suite touches the network, a real Ollama instance, a
microphone, or a model download — every external boundary (requests.post,
the Vosk/Whisper loaders, winotify, threading.Timer) is mocked at the call
site in the test that needs it.

The one piece of process-global state is transcriber's cached ASR models:
`_vosk_model` is a module-level global set on first load, and `_whisper_model`
is created dynamically (via `globals()`) the first time the whisper backend
runs, so it may not exist at all yet. Reset both around every test so one
test's cached model can't leak into the next.
"""
import pytest

import transcriber


@pytest.fixture(autouse=True)
def _reset_asr_model_cache(monkeypatch):
    monkeypatch.setattr(transcriber, "_vosk_model", None)
    monkeypatch.setattr(transcriber, "_whisper_model", None, raising=False)
    yield
