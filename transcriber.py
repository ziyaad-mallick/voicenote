"""
On-device transcription via faster-whisper or Groq API.

First call downloads the model (~140 MB for 'base') to ~/.cache/huggingface/hub.
Subsequent calls are instant.
"""

import os
import tempfile
import numpy as np
from faster_whisper import WhisperModel
from scipy.io import wavfile


_model: WhisperModel | None = None


def _get_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _model


def transcribe(
    audio: np.ndarray,
    sample_rate: int = 16000,
    model_size: str = "base",
    language: str = "en",
    device: str = "cpu",
    compute_type: str = "int8",
    backend: str = "whisper",
) -> str:
    if audio is None or len(audio) == 0:
        return ""

    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    if backend == "groq":
        return _transcribe_groq(audio, sample_rate, language)
    else:
        return _transcribe_whisper(audio, model_size, language, device, compute_type)


def _transcribe_whisper(
    audio: np.ndarray,
    model_size: str,
    language: str,
    device: str,
    compute_type: str,
) -> str:
    model = _get_model(model_size, device, compute_type)
    segments, _ = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _transcribe_groq(audio: np.ndarray, sample_rate: int, language: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(
            "GROQ_API_KEY not set. Falling back to whisper backend.",
        )
        return _transcribe_whisper(audio, "base", language, "cpu", "int8")

    try:
        import groq
    except ImportError:
        print("groq package not installed. Falling back to whisper backend.")
        return _transcribe_whisper(audio, "base", language, "cpu", "int8")

    client = groq.Groq(api_key=api_key)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        wavfile.write(tmp_path, sample_rate, (audio * 32767).astype(np.int16))

        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
            )

        return transcript.text.strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
