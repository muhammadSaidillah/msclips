"""Automated quality control on the actual rendered file. A clip only passes after these checks run."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from msclips.core.config import get_settings
from msclips.media.probe import MediaError, probe
from msclips.media.reframe import CropPlan
from msclips.media.render import OUT_FPS, OUT_H, OUT_W
from msclips.media.subtitles import estimate_line_width


async def _ffmpeg_stderr(*args: str) -> str:
    s = get_settings()
    proc = await asyncio.create_subprocess_exec(
        s.ffmpeg_bin, "-hide_banner", "-nostats", *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    return err.decode(errors="replace")


async def run_qc(
    path: Path, expected_duration: float, caption_lines: list[tuple[str, int]], caption_limit_px: float,
    plan: CropPlan, captions_enabled: bool = True,
) -> dict:
    """caption_lines: (text, font size) in the caption canvas; caption_limit_px: widest a line may be there."""
    checks: list[dict] = []

    def add(name: str, status: str, detail: str, fix: str | None = None):
        checks.append({"name": name, "status": status, "detail": detail, "fix": fix})

    if not path.exists() or path.stat().st_size == 0:
        add("file", "fail", "Output file is missing or empty.")
        return {"status": "fail", "checks": checks}
    try:
        info = await probe(path)
    except MediaError as e:
        add("file", "fail", f"Output is not a readable video: {e}")
        return {"status": "fail", "checks": checks}
    add("file", "pass", f"Readable MP4, {path.stat().st_size} bytes.")

    ok_res = info.width == OUT_W and info.height == OUT_H
    add("resolution", "pass" if ok_res else "fail", f"{info.width}x{info.height} (expected {OUT_W}x{OUT_H}, 9:16).")
    add("codec", "pass" if info.video_codec == "h264" and info.audio_codec == "aac" else "fail",
        f"video {info.video_codec}, audio {info.audio_codec}.")
    fps_ok = info.fps is not None and abs(info.fps - OUT_FPS) < 0.5
    add("frame_rate", "pass" if fps_ok else "fail", f"{info.fps} fps (expected {OUT_FPS}).")
    d_err = abs(info.duration_s - expected_duration)
    add("duration", "pass" if d_err < 0.25 else "fail",
        f"{info.duration_s:.2f}s (expected {expected_duration:.2f}s, off by {d_err:.2f}s).")
    add("audio", "pass" if info.has_audio else "fail", "Audio track present." if info.has_audio else "No audio track.")

    # Black and frozen frames.
    err = await _ffmpeg_stderr("-i", str(path), "-an", "-vf",
                               "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=0.003:d=2", "-f", "null", "-")
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)
    freezes = re.findall(r"freeze_start: ([\d.]+)", err)
    add("black_frames", "warn" if blacks else "pass",
        f"{len(blacks)} black section(s) ≥0.5s." if blacks else "No black sections.",
        "Adjust the start/end so the clip avoids black footage." if blacks else None)
    add("frozen_frames", "warn" if freezes else "pass",
        f"{len(freezes)} frozen section(s) ≥2s." if freezes else "No frozen sections.",
        "Check the source; static slides or a stalled camera can cause this." if freezes else None)

    # Audio clipping and loudness.
    err = await _ffmpeg_stderr("-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-")
    m = re.search(r"max_volume: (-?[\d.]+) dB", err)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", err)
    if m:
        peak = float(m.group(1))
        add("audio_clipping", "warn" if peak >= -0.1 else "pass", f"Peak {peak:.1f} dBFS.",
            "Lower the gain or enable a limiter." if peak >= -0.1 else None)
    if mean:
        mv = float(mean.group(1))
        add("audio_level", "warn" if mv < -40 else "pass", f"Mean level {mv:.1f} dB.",
            "Audio is very quiet or mostly silent; check the source segment." if mv < -40 else None)

    # Subtitles: present and within the safe area.
    if caption_lines:
        too_wide = [t for t, size in caption_lines if estimate_line_width(t, size) > caption_limit_px]
        add("subtitle_overflow", "warn" if too_wide else "pass",
            f"{len(too_wide)} caption line(s) may not fit the safe width." if too_wide
            else f"{len(caption_lines)} caption lines fit the safe width.",
            "Use a calmer style (Clean) or shorter phrases." if too_wide else None)
    elif captions_enabled:
        add("subtitle_overflow", "warn", "No captions were generated for this clip.", "Check the transcript for this range.")

    # Face kept inside the crop.
    if plan.mode == "face" and plan.face_boxes:
        outside = 0
        for t, x, y, w, h in plan.face_boxes:
            shot = next((s for s in plan.shots if s.start <= t < s.end), plan.shots[-1])
            cx0 = plan.x_for(shot.center_x) / plan.src_w
            cx1 = cx0 + plan.crop_w / plan.src_w
            if x < cx0 - 0.01 or x + w > cx1 + 0.01:
                outside += 1
        ratio = outside / len(plan.face_boxes)
        add("face_framing", "warn" if ratio > 0.1 else "pass",
            f"Main face inside the frame in {100 - ratio * 100:.0f}% of sampled frames.",
            "Two people far apart may need a split layout (planned)." if ratio > 0.1 else None)
    elif plan.mode == "center":
        add("face_framing", "warn", "No face detected; used a centre crop.", "Check that the subject is centred.")

    status = "fail" if any(c["status"] == "fail" for c in checks) else "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    return {"status": status, "checks": checks}
