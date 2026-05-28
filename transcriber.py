"""
On-device transcription via faster-whisper.

First call downloads the model (~140 MB for 'base') to ~/.cache/huggingface/hub.
Subsequent calls are instant.
"""

import numpy as np
from faster_whisper import WhisperModel


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
) -> str:
    if audio is None or len(audio) == 0:
        return ""

    # faster-whisper expects float32 mono at 16 kHz
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    model = _get_model(model_size, device, compute_type)
    segments, _ = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=True,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()
