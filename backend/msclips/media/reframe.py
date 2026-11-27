"""Choose a 9:16 crop that keeps the speaker's face in frame.

Faces are detected (YuNet) on frames sampled at 2 fps. The horizontal face position is smoothed and
split into stable "shots": the crop holds still within a shot and cuts (never pans jerkily) when the
subject moves far or the active face changes. Falls back to a centre crop when no face is found.
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from msclips.core.config import get_settings

MODEL_PATH = Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
SAMPLE_FPS = 2
ANALYSIS_W = 640
MIN_SHOT_S = 2.0
MOVE_THRESHOLD = 0.12  # fraction of source width the face must move before the crop re-positions


@dataclass
class Shot:
    start: float
    end: float
    center_x: float  # 0-1, fraction of source width


@dataclass
class CropPlan:
    mode: str  # "face" | "center" | "fit"
    src_w: int
    src_h: int
    crop_w: int
    crop_h: int
    shots: list[Shot] = field(default_factory=list)
    face_frames: int = 0
    sampled_frames: int = 0
    face_boxes: list[tuple[float, float, float, float, float]] = field(default_factory=list)  # t, x, y, w, h (0-1)

    def x_for(self, center_x: float) -> int:
        x = round(center_x * self.src_w - self.crop_w / 2)
        return int(max(0, min(self.src_w - self.crop_w, x)))

    def ffmpeg_crop_x(self) -> str:
        if not self.shots:
            return str(self.x_for(0.5))
        expr = str(self.x_for(self.shots[-1].center_x))
        for shot in reversed(self.shots[:-1]):
            expr = f"if(lt(t\\,{shot.end:.3f})\\,{self.x_for(shot.center_x)}\\,{expr})"
        return expr

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("face_boxes")
        return d


async def _sample_frames(path: Path, start: float, duration: float, src_w: int, src_h: int):
    s = get_settings()
    h = round(ANALYSIS_W * src_h / src_w / 2) * 2
    proc = await asyncio.create_subprocess_exec(
        s.ffmpeg_bin, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(path),
        "-map", "0:v:0", "-vf", f"fps={SAMPLE_FPS},scale={ANALYSIS_W}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    frame_bytes = ANALYSIS_W * h * 3
    n = len(out) // frame_bytes
    return [np.frombuffer(out, np.uint8, frame_bytes, i * frame_bytes).reshape(h, ANALYSIS_W, 3) for i in range(n)], h


def _detect(frames, w: int, h: int):
    import cv2

    det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (w, h), score_threshold=0.7)
    results = []
    for f in frames:
        _, faces = det.detect(f)
        boxes = []
        if faces is not None:
            for x, y, bw, bh, *_rest, score in faces:
                boxes.append((float(x) / w, float(y) / h, float(bw) / w, float(bh) / h, float(score)))
        results.append(boxes)
    return results


def plan_shots(track: list[tuple[float, float | None]], duration: float) -> list[Shot]:
    """track: (t, face centre x or None). Returns stable shots with hard cuts between them."""
    pts = [(t, x) for t, x in track if x is not None]
    if not pts:
        return []
    # Fill gaps with the last known position, then median-smooth to remove detector noise.
    filled, last = [], pts[0][1]
    for t, x in track:
        last = x if x is not None else last
        filled.append((t, last))
    xs = [x for _, x in filled]
    k = 2
    smooth = [statistics.median(xs[max(0, i - k) : i + k + 1]) for i in range(len(xs))]

    shots: list[Shot] = []
    cur_start, cur_vals = 0.0, [smooth[0]]
    for (t, _), x in zip(filled[1:], smooth[1:]):
        anchor = statistics.median(cur_vals)
        if abs(x - anchor) > MOVE_THRESHOLD and t - cur_start >= MIN_SHOT_S:
            shots.append(Shot(cur_start, t, anchor))
            cur_start, cur_vals = t, [x]
        else:
            cur_vals.append(x)
    shots.append(Shot(cur_start, duration, statistics.median(cur_vals)))
    # Merge a too-short final shot into the previous one.
    if len(shots) > 1 and shots[-1].end - shots[-1].start < MIN_SHOT_S:
        last = shots.pop()
        shots[-1].end = last.end
    return shots


async def plan_crop(path: Path, start: float, duration: float, src_w: int, src_h: int) -> CropPlan:
    target = 9 / 16
    if src_w / src_h <= target + 1e-3:
        # Already vertical or narrower: scale to width and pad/crop vertically.
        return CropPlan("fit", src_w, src_h, src_w, src_h)
    crop_h = src_h - src_h % 2
    crop_w = int(round(crop_h * target / 2) * 2)
    plan = CropPlan("center", src_w, src_h, crop_w, crop_h)
    if not MODEL_PATH.exists():
        return plan
    frames, h = await _sample_frames(path, start, duration, src_w, src_h)
    if not frames:
        return plan
    detections = await asyncio.to_thread(_detect, frames, ANALYSIS_W, h)
    track: list[tuple[float, float | None]] = []
    for i, boxes in enumerate(detections):
        t = i / SAMPLE_FPS
        if boxes:
            x, y, bw, bh, _ = max(boxes, key=lambda b: b[2] * b[3])  # largest face = most likely speaker
            track.append((t, x + bw / 2))
            plan.face_boxes.append((t, x, y, bw, bh))
        else:
            track.append((t, None))
    plan.sampled_frames = len(detections)
    plan.face_frames = sum(1 for b in detections if b)
    if plan.face_frames >= max(2, 0.3 * plan.sampled_frames):
        plan.mode = "face"
        plan.shots = plan_shots(track, duration)
    return plan
