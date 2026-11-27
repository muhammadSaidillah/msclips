import asyncio

import numpy as np

from msclips.core.config import get_settings
from msclips.media.probe import MediaError


async def decode_pcm_16k(path) -> np.ndarray:
    """Decode the first audio stream to 16 kHz mono float32 (what Whisper expects)."""
    s = get_settings()
    proc = await asyncio.create_subprocess_exec(
        s.ffmpeg_bin, "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000",
        "-f", "f32le", "-", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise MediaError("Could not decode the audio track: " + err.decode(errors="replace").strip()[-300:])
    audio = np.frombuffer(out, dtype=np.float32)
    if audio.size < 16000:
        raise MediaError("The audio track is shorter than one second; nothing to transcribe.")
    return audio
