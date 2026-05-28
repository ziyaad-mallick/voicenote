import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

import vosk

vosk.SetLogLevel(-1)

_vosk_model = None


def ensure_vosk_model(progress_callback=None) -> Path:
    model_dir = Path.home() / ".voicenote" / "models" / "vosk-small-en"

    if model_dir.exists() and list(model_dir.iterdir()):
        return model_dir

    model_dir.parent.mkdir(parents=True, exist_ok=True)

    url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    zip_path = model_dir.parent / "vosk-model.zip"

    def reporthook(block_num, block_size, total_size):
        if progress_callback is None:
            return
        downloaded = block_num * block_size
        percent = min(100, int(100 * downloaded / total_size)) if total_size > 0 else 0
        progress_callback(percent)

    urllib.request.urlretrieve(url, zip_path, reporthook)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(model_dir.parent)

    extracted_dir = model_dir.parent / "vosk-model-small-en-us-0.15"
    if extracted_dir.exists():
        model_dir.mkdir(exist_ok=True)
        for item in extracted_dir.iterdir():
            shutil.move(str(item), str(model_dir / item.name))
        extracted_dir.rmdir()

    zip_path.unlink()

    return model_dir


def _get_vosk_model() -> vosk.Model:
    global _vosk_model
    if _vosk_model is None:
        model_dir = ensure_vosk_model()
        _vosk_model = vosk.Model(str(model_dir))
    return _vosk_model


def _transcribe_vosk(audio: np.ndarray, sample_rate: int) -> str:
    model = _get_vosk_model()
    recognizer = vosk.KaldiRecognizer(model, sample_rate)

    audio_bytes = (audio * 32767).astype(np.int16).tobytes()
    recognizer.AcceptWaveform(audio_bytes)

    result_json = recognizer.FinalResult()
    result = json.loads(result_json)

    return result.get("text", "").strip()


def _transcribe_whisper(
    audio: np.ndarray,
    model_size: str,
    language: str,
    device: str,
    compute_type: str,
) -> str:
    from faster_whisper import WhisperModel

    global _whisper_model
    if "_whisper_model" not in globals():
        _whisper_model = None

    if _whisper_model is None:
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments, _ = _whisper_model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _transcribe_groq(audio: np.ndarray, sample_rate: int, language: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not set. Falling back to vosk backend.")
        return _transcribe_vosk(audio, sample_rate)

    try:
        import groq
    except ImportError:
        print("groq package not installed. Falling back to vosk backend.")
        return _transcribe_vosk(audio, sample_rate)

    from scipy.io import wavfile

    client = groq.Groq(api_key=api_key)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        wavfile.write(tmp_path, sample_rate, (audio * 32767).astype(np.int16))

        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
            )

        return transcript.text.strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def transcribe(
    audio: np.ndarray,
    sample_rate: int = 16000,
    model_size: str = "small",
    language: str = "en",
    device: str = "cpu",
    compute_type: str = "int8",
    backend: str = "vosk",
) -> str:
    if audio is None or len(audio) == 0:
        return ""

    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    if backend == "vosk":
        return _transcribe_vosk(audio, sample_rate)
    elif backend == "whisper":
        return _transcribe_whisper(audio, model_size, language, device, compute_type)
    elif backend == "groq":
        return _transcribe_groq(audio, sample_rate, language)
    else:
        raise ValueError(f"Unknown backend: {backend}")
