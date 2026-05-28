"""
Mic recording via sounddevice.

Usage:
    rec = Recorder(sample_rate=16000)
    rec.start()
    ...
    audio_np = rec.stop()   # float32 numpy array, shape (N,)
"""

import threading
import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self.is_recording = False

    def _callback(self, indata: np.ndarray, frames, time, status):
        with self._lock:
            self._chunks.append(indata.copy())

    def start(self):
        self._chunks.clear()
        self.is_recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
            blocksize=1024,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.is_recording = False
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype="float32")
            audio = np.concatenate(self._chunks, axis=0)
        # Flatten to 1-D mono
        return audio[:, 0] if audio.ndim == 2 else audio

    def get_rms(self) -> float:
        """Current RMS volume (0-1) for waveform display."""
        with self._lock:
            if not self._chunks:
                return 0.0
            recent = self._chunks[-1]
        return float(np.sqrt(np.mean(recent ** 2)))
