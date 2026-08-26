"""transcriber.py: three swappable ASR backends behind one `transcribe()` call.

Two things are tested here because they're public claims in the README:

1. Model caching — Vosk and Whisper are loaded once into a module-level
   global and reused, because paying model-init cost on every note is what
   turns a 4-second note into a 15-second one. `ensure_vosk_model` /
   `vosk.Model` and `faster_whisper.WhisperModel` are mocked, and the loader
   is called twice in a row to prove the second call is served from cache.
2. Three backends, one interface — `transcribe(..., backend=...)` picks
   between vosk/whisper/groq, and groq falls back to vosk when no API key is
   configured so the offline promise holds even if `groq` stays selected.

No real model is ever loaded and no network call is ever made — every
backend implementation is replaced at its boundary (the vosk/faster_whisper
model classes, or the private `_transcribe_*` functions).
"""
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

import transcriber as t


def _audio(n=1600):
    return np.zeros(n, dtype=np.float32)


# -- model caching ----------------------------------------------------------

def test_vosk_model_is_loaded_once_across_two_calls(monkeypatch):
    ensure_calls = []
    monkeypatch.setattr(
        t,
        "ensure_vosk_model",
        lambda progress_callback=None: ensure_calls.append(1) or Path("fake-model-dir"),
    )

    init_calls = []

    class FakeVoskModel:
        def __init__(self, path):
            init_calls.append(path)

    # `vosk` is imported lazily by t._vosk(), so there is no module-level
    # attribute to patch -- stand in for the module itself.
    monkeypatch.setattr(
        t, "_vosk", lambda: SimpleNamespace(Model=FakeVoskModel)
    )

    first = t._get_vosk_model()
    second = t._get_vosk_model()

    assert len(ensure_calls) == 1, "the model directory should only be resolved once"
    assert len(init_calls) == 1, "vosk.Model(...) should only be constructed once"
    assert first is second


def test_whisper_model_is_loaded_once_across_two_calls(monkeypatch):
    # This one patches a class ON the real package, so unlike the vosk test it
    # cannot run without faster_whisper present. Skip rather than fail, so the
    # suite stays runnable without the ASR stack installed.
    faster_whisper = pytest.importorskip("faster_whisper")

    init_calls = []

    class FakeSegment:
        def __init__(self, text):
            self.text = text

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            init_calls.append((model_size, device, compute_type))

        def transcribe(self, audio, language, beam_size, vad_filter):
            return [FakeSegment("hello world")], None

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)

    audio = _audio()
    first = t._transcribe_whisper(audio, "small", "en", "cpu", "int8")
    second = t._transcribe_whisper(audio, "small", "en", "cpu", "int8")

    assert len(init_calls) == 1, "WhisperModel(...) should only be constructed once"
    assert first == second == "hello world"


# -- transcribe() dispatch: three backends, one interface --------------------

def test_transcribe_dispatches_to_the_vosk_backend(monkeypatch):
    monkeypatch.setattr(t, "_transcribe_vosk", lambda audio, sample_rate: "vosk result")
    result = t.transcribe(_audio(), backend="vosk")
    assert result == "vosk result"


def test_transcribe_dispatches_to_the_whisper_backend(monkeypatch):
    monkeypatch.setattr(
        t,
        "_transcribe_whisper",
        lambda audio, model_size, language, device, compute_type: "whisper result",
    )
    result = t.transcribe(_audio(), backend="whisper")
    assert result == "whisper result"


def test_transcribe_dispatches_to_the_groq_backend(monkeypatch):
    monkeypatch.setattr(
        t, "_transcribe_groq", lambda audio, sample_rate, language: "groq result"
    )
    result = t.transcribe(_audio(), backend="groq")
    assert result == "groq result"


def test_an_unknown_backend_raises_value_error():
    with pytest.raises(ValueError):
        t.transcribe(_audio(), backend="mystery")


def test_empty_audio_short_circuits_without_touching_any_backend(monkeypatch):
    called = []
    monkeypatch.setattr(t, "_transcribe_vosk", lambda *a, **kw: called.append(1))
    result = t.transcribe(np.zeros(0, dtype=np.float32), backend="vosk")
    assert result == ""
    assert called == []


def test_none_audio_short_circuits_to_empty_string():
    assert t.transcribe(None, backend="vosk") == ""


def test_non_float32_audio_is_cast_before_reaching_the_backend(monkeypatch):
    captured = {}

    def fake_vosk(audio, sample_rate):
        captured["dtype"] = audio.dtype
        return "ok"

    monkeypatch.setattr(t, "_transcribe_vosk", fake_vosk)
    int_audio = np.array([1, 2, 3], dtype=np.int16)
    t.transcribe(int_audio, backend="vosk")

    assert captured["dtype"] == np.float32


# -- groq's offline fallback (the specific claim the README makes) -----------

def test_groq_backend_without_an_api_key_falls_back_to_vosk(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    vosk_calls = []
    monkeypatch.setattr(
        t,
        "_transcribe_vosk",
        lambda audio, sample_rate: vosk_calls.append(1) or "vosk fallback text",
    )

    result = t._transcribe_groq(_audio(), sample_rate=16000, language="en")

    assert result == "vosk fallback text"
    assert vosk_calls == [1]
