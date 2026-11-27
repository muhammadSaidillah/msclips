"""ffprobe/ffmpeg wrappers. Pure functions: no DB, no storage."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

from clipforge.core.config import get_settings


class MediaError(Exception):
    """The file is not a usable video. Deterministic: retrying will not help."""


class ToolError(RuntimeError):
    """ffmpeg/ffprobe failed for an environmental reason (may be retryable)."""


@dataclass
class VideoInfo:
    container: str | None
    duration_s: float
    width: int
    height: int
    rotation: int
    display_width: int
    display_height: int
    aspect_ratio: str
    orientation: str
    fps: float | None
    video_codec: str | None
    pixel_format: str | None
    bit_rate: int | None
    has_audio: bool
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    audio_track_count: int
    raw_probe: dict

    def as_columns(self) -> dict:
        return asdict(self)


async def _run(*args: str, timeout: float = 300) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as e:
        raise ToolError(f"{args[0]} not installed") from e
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolError(f"{Path(args[0]).name} timed out after {timeout}s") from None
    return proc.returncode or 0, out, err


def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    try:
        v = float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return None
    return round(v, 3) if v > 0 else None


def _rotation(stream: dict) -> int:
    rot = 0
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            rot = int(tags["rotate"])
        except ValueError:
            pass
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rot = int(sd["rotation"])
            except (TypeError, ValueError):
                pass
    return rot % 360


COMMON_RATIOS = {
    "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4, "1:1": 1.0,
    "21:9": 21 / 9, "4:5": 4 / 5, "5:4": 5 / 4, "3:2": 3 / 2, "2:3": 2 / 3,
}


def aspect_label(w: int, h: int) -> str:
    r = w / h
    for label, val in COMMON_RATIOS.items():
        if abs(r - val) / val < 0.02:
            return label
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def orientation(w: int, h: int) -> str:
    if abs(w - h) / max(w, h) < 0.02:
        return "square"
    return "landscape" if w > h else "portrait"


def parse_probe(data: dict) -> VideoInfo:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    videos = [
        s for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos:
        raise MediaError("No video stream found. The file may be audio-only or not a video.")
    v = videos[0]
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if w <= 0 or h <= 0:
        raise MediaError("Video stream has no valid resolution.")

    duration = None
    for cand in (fmt.get("duration"), v.get("duration")):
        try:
            if cand is not None and float(cand) > 0:
                duration = float(cand)
                break
        except ValueError:
            continue
    if duration is None:
        raise MediaError("Could not determine video duration. The file may be truncated or corrupt.")

    rot = _rotation(v)
    dw, dh = (h, w) if rot in (90, 270) else (w, h)
    # Honour non-square pixels (SAR) for display size
    sar = v.get("sample_aspect_ratio")
    if sar and sar not in ("0:1", "1:1"):
        try:
            num, den = (int(x) for x in sar.split(":"))
            if num > 0 and den > 0:
                if rot in (90, 270):
                    dh = round(dh * num / den)
                else:
                    dw = round(dw * num / den)
        except ValueError:
            pass

    fps = _parse_rate(v.get("avg_frame_rate")) or _parse_rate(v.get("r_frame_rate"))
    bit_rate = fmt.get("bit_rate") or v.get("bit_rate")
    a = audios[0] if audios else None
    return VideoInfo(
        container=fmt.get("format_name"),
        duration_s=round(duration, 3),
        width=w,
        height=h,
        rotation=rot,
        display_width=dw,
        display_height=dh,
        aspect_ratio=aspect_label(dw, dh),
        orientation=orientation(dw, dh),
        fps=fps,
        video_codec=v.get("codec_name"),
        pixel_format=v.get("pix_fmt"),
        bit_rate=int(bit_rate) if bit_rate and str(bit_rate).isdigit() else None,
        has_audio=a is not None,
        audio_codec=a.get("codec_name") if a else None,
        audio_channels=int(a["channels"]) if a and a.get("channels") else None,
        audio_sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        audio_track_count=len(audios),
        raw_probe=data,
    )


async def probe(path: Path) -> VideoInfo:
    s = get_settings()
    code, out, err = await _run(
        s.ffprobe_bin, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path), timeout=120,
    )
    if code != 0:
        msg = err.decode(errors="replace").strip().splitlines()
        raise MediaError(
            "The file could not be read as a video"
            + (f": {msg[-1]}" if msg else ".")
        )
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise ToolError("ffprobe returned invalid JSON") from e
    return parse_probe(data)


async def verify_decodable(path: Path, at_s: float) -> None:
    """Decode one frame to prove the video stream is actually decodable (headers can lie)."""
    s = get_settings()
    code, _, err = await _run(
        s.ffmpeg_bin, "-v", "error", "-ss", f"{at_s:.3f}", "-i", str(path),
        "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-", timeout=120,
    )
    if code != 0:
        raise MediaError("Video stream could not be decoded: " + err.decode(errors="replace").strip()[-300:])


async def make_thumbnail(path: Path, out: Path, at_s: float, max_side: int = 640) -> None:
    s = get_settings()
    vf = f"scale='if(gt(iw,ih),{max_side},-2)':'if(gt(iw,ih),-2,{max_side})'"
    code, _, err = await _run(
        s.ffmpeg_bin, "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(path),
        "-map", "0:v:0", "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out), timeout=120,
    )
    if code != 0 or not out.exists() or out.stat().st_size == 0:
        raise MediaError("Could not extract a thumbnail frame: " + err.decode(errors="replace").strip()[-300:])
