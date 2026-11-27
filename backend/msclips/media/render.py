"""Server-side clip rendering with FFmpeg: cut, 9:16 reframe, editing style (grade, zoom, captions,
showcase layout), loudness, encode."""

from __future__ import annotations

import asyncio
import re
import statistics
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from msclips.core.config import get_settings
from msclips.media.probe import MediaError, ToolError
from msclips.media.reframe import CropPlan, Shot
from msclips.media.styles import GRADES, STYLES, EditStyle
from msclips.media.subtitles import Word, chunk_words, pick_keyword

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
LAND_W, LAND_H = 1920, 1080

DYNAMIC_LEVELS = (1.0, 1.22, 1.1, 1.32)


def _filter_path(p: Path) -> str:
    # Escape for use inside an ffmpeg filtergraph option value.
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def median_center(plan: CropPlan) -> float:
    if not plan.shots:
        return 0.5
    weighted = []
    for s in plan.shots:
        weighted += [s.center_x] * max(1, round((s.end - s.start) * 10))
    return statistics.median(weighted)


def static_plan(plan: CropPlan, duration: float) -> CropPlan:
    """One fixed crop at the speaker's median position (no tracking cuts)."""
    if plan.mode != "face" or not plan.shots:
        return plan
    return replace(plan, shots=[Shot(0.0, duration, median_center(plan))])


def zoom_schedule(kind: str, words: list[Word], duration: float) -> list[tuple[float, float]]:
    """[(start time, zoom)] with hard cuts. "dynamic": shot size changes every ~2-4 s at phrase starts.
    "punch": zoom in on keywords (1.12/1.18 alternating, at least 3 s apart)."""
    if kind == "none" or not words:
        return [(0.0, 1.0)]
    chunks = chunk_words(words, 24, 4)
    out = [(0.0, 1.0)]
    if kind == "dynamic":
        level, shot_start = 0, 0.0
        for c in chunks:
            for w in c:
                t = w.start
                at_phrase_start = w is c[0]
                if duration - t < 1.5:
                    break
                if (at_phrase_start and t - shot_start >= 1.8) or t - shot_start >= 4.0:
                    level = (level + 1) % len(DYNAMIC_LEVELS)
                    out.append((round(t, 3), DYNAMIC_LEVELS[level]))
                    shot_start = t
        return out
    last, alt = -10.0, 0
    for c in chunks:
        kw = c[pick_keyword(c)]
        if kw.start < 1.0 or kw.start - last < 3.0 or duration - kw.start < 1.0:
            continue
        z = (1.12, 1.18)[alt % 2]
        alt += 1
        out.append((round(kw.start, 3), z))
        out.append((round(max(c[-1].end, kw.start + 0.8), 3), 1.0))
        last = kw.start
    return out


def zoom_filter(schedule: list[tuple[float, float]], w: int, h: int, ax: float = 0.5, ay: float = 0.32) -> str:
    if len(schedule) <= 1 and schedule[0][1] == 1.0:
        return ""
    expr = f"{schedule[-1][1]}"
    for (t0, z), (t1, _) in reversed(list(zip(schedule[:-1], schedule[1:]))):
        expr = f"if(lt(it,{t1}),{z},{expr})"
    return (f"zoompan=z='{expr}':x='iw*{ax}-iw/zoom*{ax}':y='ih*{ay}-ih/zoom*{ay}'"
            f":d=1:s={w}x{h}:fps={OUT_FPS}")


def _base_vertical(plan: CropPlan) -> str:
    if plan.mode == "fit":
        return (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black")
    return (f"crop={plan.crop_w}:{plan.crop_h}:'{plan.ffmpeg_crop_x()}':{(plan.src_h - plan.crop_h) // 2},"
            f"scale={OUT_W}:{OUT_H}:flags=lanczos")


def _base_landscape() -> str:
    return (f"scale={LAND_W}:{LAND_H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={LAND_W}:{LAND_H}")


def _styled(base: str, style: EditStyle, zoom: str, ass_path: Path | None) -> str:
    chain = [base, "setsar=1", f"fps={OUT_FPS}"]
    if zoom:
        chain.append(zoom)
    if GRADES.get(style.grade):
        chain.append(GRADES[style.grade])
    if style.grain:
        chain.append("noise=alls=5:allf=t")
    if ass_path is not None:
        chain.append(f"ass='{_filter_path(ass_path)}':fontsdir='{_filter_path(FONTS_DIR)}'")
    return ",".join(chain)


def build_filtergraph(
    plan: CropPlan, ass_path: Path | None, duration: float, style: EditStyle | None = None,
    zoom: list[tuple[float, float]] | None = None, showcase_assets: dict[str, Path] | None = None,
) -> str:
    """Inputs: 0 = source. Showcase layouts also use 1 = background, 2 = after mask, 3 = raw mask."""
    style = style or STYLES["bold"]
    sched = zoom or [(0.0, 1.0)]
    fade_out = max(0.0, duration - 0.12)
    a = f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.04,afade=t=out:st={fade_out:.3f}:d=0.12,aresample=48000[a]"
    sc = style.showcase
    if sc is None:
        v = "[0:v]" + _styled(_base_vertical(plan), style, zoom_filter(sched, OUT_W, OUT_H), ass_path) + "[v]"
        return f"{v};{a}"

    assert showcase_assets is not None
    ax, ay, aw, ah = sc.after
    rx, ry, rw, rh = sc.raw
    if sc.landscape:
        face_x = statistics.median([b[1] + b[3] / 2 for b in plan.face_boxes]) if plan.face_boxes else 0.5
        after_base = _base_landscape()
        zf = zoom_filter(sched, LAND_W, LAND_H, ax=face_x, ay=0.35)
        raw_base = _base_landscape()
    else:
        after_base = _base_vertical(plan)
        zf = zoom_filter(sched, OUT_W, OUT_H)
        raw_base = _base_vertical(static_plan(plan, duration))
    raw_chain = [raw_base, "setsar=1", f"fps={OUT_FPS}", f"scale={rw}:{rh}:flags=lanczos"]
    if sc.raw_mono:
        raw_chain.append("hue=s=0")
    labels = showcase_assets["labels"]
    v = (
        "[0:v]split=2[va][vr];"
        f"[va]{_styled(after_base, style, zf, ass_path)},scale={aw}:{ah}:flags=lanczos,format=rgba[a0];"
        "[2:v]format=gray[m2];[a0][m2]alphamerge[ac];"
        f"[vr]{','.join(raw_chain)},format=rgba[r0];"
        "[3:v]format=gray[m3];[r0][m3]alphamerge[rc];"
        f"[1:v]format=rgba[bg];[bg][rc]overlay={rx}:{ry}[b1];[b1][ac]overlay={ax}:{ay}:shortest=1,"
        f"ass='{_filter_path(labels)}':fontsdir='{_filter_path(FONTS_DIR)}',format=yuv420p[v]"
    )
    return f"{v};{a}"


async def render_clip(
    src: Path, out: Path, start: float, end: float, plan: CropPlan, ass_path: Path | None,
    on_progress: Callable[[float], None] | None = None, style: EditStyle | None = None,
    zoom: list[tuple[float, float]] | None = None, showcase_assets: dict[str, Path] | None = None,
) -> None:
    s = get_settings()
    duration = end - start
    inputs = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src)]
    if style is not None and style.showcase is not None:
        assert showcase_assets is not None
        for key in ("background", "after_mask", "raw_mask"):
            inputs += ["-loop", "1", "-framerate", str(OUT_FPS), "-t", f"{duration:.3f}", "-i", str(showcase_assets[key])]
    args = [
        s.ffmpeg_bin, "-v", "error", "-y", "-nostdin", "-progress", "pipe:1", *inputs,
        "-filter_complex", build_filtergraph(plan, ass_path, duration, style, zoom, showcase_assets),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(OUT_FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    assert proc.stdout is not None
    async for line in proc.stdout:
        m = re.match(rb"out_time_us=(\d+)", line)
        if m and on_progress:
            on_progress(min(1.0, int(m.group(1)) / 1e6 / duration))
    err = await proc.stderr.read() if proc.stderr else b""
    code = await proc.wait()
    if code != 0:
        msg = err.decode(errors="replace").strip()[-600:]
        if "No such file" in msg or "Invalid data" in msg:
            raise MediaError(f"Render failed: {msg}")
        raise ToolError(f"ffmpeg render failed: {msg}")
