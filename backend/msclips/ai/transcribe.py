"""Speech-to-text with word timestamps using faster-whisper (runs locally on CPU or GPU)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from msclips.core.config import get_settings

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            s = get_settings()
            _model = WhisperModel(
                s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type,
                cpu_threads=s.whisper_cpu_threads,
            )
        return _model


@dataclass
class TranscriptResult:
    language: str
    language_probability: float | None
    duration_s: float
    text: str
    segments: list[dict]
    engine: str


def transcribe(audio: np.ndarray, language: str | None, on_progress: Callable[[float], None]) -> TranscriptResult:
    """Blocking; call via asyncio.to_thread. `on_progress` gets the fraction of audio processed (0-1)."""
    s = get_settings()
    model = _get_model()
    duration = audio.size / 16000
    seg_iter, info = model.transcribe(
        audio, language=language, word_timestamps=True, vad_filter=True, beam_size=5,
        condition_on_previous_text=False,
    )
    segments: list[dict] = []
    for seg in seg_iter:  # generator: decoding happens as we iterate, so progress is real
        words = [
            {"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        if not words:
            continue
        segments.append(
            {"id": len(segments), "start": round(seg.start, 3), "end": round(seg.end, 3),
             "text": seg.text.strip(), "words": words}
        )
        on_progress(min(1.0, seg.end / duration))
    return TranscriptResult(
        language=info.language,
        language_probability=round(info.language_probability, 3) if info.language_probability else None,
        duration_s=round(duration, 3),
        text=" ".join(x["text"] for x in segments),
        segments=segments,
        engine=f"faster-whisper:{s.whisper_model}",
    )
