"""Static assets for Before/After showcase layouts: background, card shadows, label pills and card masks."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from msclips.media.styles import Showcase
from msclips.media.subtitles import ass_color, estimate_line_width, tag_color

W, H = 1080, 1920
PILL_H, PILL_SIZE = 58, 30


def _rounded(w: int, h: int, r: int) -> np.ndarray:
    """Anti-aliased rounded-rectangle mask (uint8, 0/255)."""
    import cv2

    s = 4
    m = np.zeros((h * s, w * s), np.uint8)
    r4 = max(1, r * s)
    cv2.rectangle(m, (r4, 0), (w * s - r4, h * s), 255, -1)
    cv2.rectangle(m, (0, r4), (w * s, h * s - r4), 255, -1)
    for cx, cy in ((r4, r4), (w * s - r4, r4), (r4, h * s - r4), (w * s - r4, h * s - r4)):
        cv2.circle(m, (cx, cy), r4, 255, -1)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)


def _paste_alpha(img: np.ndarray, mask: np.ndarray, x: int, y: int, color: tuple[int, int, int], opacity: float) -> None:
    h, w = mask.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    m = mask[y0 - y : y1 - y, x0 - x : x1 - x].astype(np.float32)[..., None] / 255 * opacity
    region = img[y0:y1, x0:x1].astype(np.float32)
    img[y0:y1, x0:x1] = (region * (1 - m) + np.array(color, np.float32) * m).astype(np.uint8)


def _background(kind: str) -> np.ndarray:
    import cv2

    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    if kind == "white":
        base = 236 + 11 * yy + 0 * xx  # light grey top -> whiter bottom
        light = np.zeros((H, W), np.float32)
        # Diagonal window light: six soft panes, bottom-left to top-right.
        for i in range(6):
            pane = np.zeros((H, W), np.uint8)
            cx, cy = 140 + i * 150, 1500 - i * 190
            box = cv2.boxPoints(((cx, cy), (110, 900), -38))
            cv2.fillPoly(pane, [box.astype(np.int32)], 255)
            light += pane.astype(np.float32) / 255
        light = cv2.GaussianBlur(light, (0, 0), 28)
        img = np.clip(base + 9 * light, 0, 255)
        return np.repeat(img[..., None], 3, axis=2).astype(np.uint8)
    if kind == "dark":
        d = np.sqrt(((xx - 0.5) * 1.2) ** 2 + (yy - 0.22) ** 2)
        img = np.clip(44 - 34 * d, 12, 44)
        rng = np.random.default_rng(7)
        img = img + rng.normal(0, 2.2, (H, W)).astype(np.float32)
        return np.repeat(np.clip(img, 0, 255)[..., None], 3, axis=2).astype(np.uint8)
    return np.zeros((H, W, 3), np.uint8)


def pill_width(text: str) -> int:
    return int(22 + 16 + 12 + estimate_line_width(text, PILL_SIZE) * 0.92 + 24)


def _label_pos(card: tuple[int, int, int, int], kind: str) -> tuple[int, int]:
    x, y, _, _ = card
    return (x + 4, y - PILL_H - 16) if kind == "pill" else (x + 4, y - 22)


def make_assets(sc: Showcase, tmpdir: Path) -> dict[str, Path]:
    """Writes background.png, after_mask.png, raw_mask.png and labels.ass; returns their paths."""
    import cv2

    bg = _background(sc.background)
    shadow_strength = 0.28 if sc.background == "white" else 0.55
    cards = [(sc.raw, sc.raw_radius), (sc.after, sc.after_radius)]
    if not sc.after_on_top:
        cards.reverse()
    for (x, y, w, h), r in cards:
        pad = 90  # room for the blur to fade out
        sh = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
        sh[pad : pad + h, pad : pad + w] = _rounded(w, h, r)
        sh = cv2.GaussianBlur(sh, (0, 0), 26)
        _paste_alpha(bg, sh, x - pad, y - pad + 24, (0, 0, 0), shadow_strength)

    labels = [(sc.raw, sc.raw_label, "#FF3B30"), (sc.after, sc.after_label, "#30D158")]
    events = []
    for card, text, dot in labels:
        lx, ly = _label_pos(card, sc.label_kind)
        if sc.label_kind == "pill":
            pw = pill_width(text)
            _paste_alpha(bg, _rounded(pw, PILL_H, PILL_H // 2), lx, ly, (24, 24, 24), 1.0)
            events.append(f"Dialogue: 0,0:00:00.00,9:00:00.00,Pill,,0,0,0,,{{\\an4\\pos({lx + 22},{ly + PILL_H // 2})}}"
                          f"{{\\c{tag_color(dot)}}}●{{\\c&HFFFFFF&}} {text}")
        else:
            events.append(f"Dialogue: 0,0:00:00.00,9:00:00.00,Label,,0,0,0,,{{\\an1\\pos({lx},{ly})}}{text}")

    paths = {
        "background": tmpdir / "showcase_bg.png",
        "after_mask": tmpdir / "after_mask.png",
        "raw_mask": tmpdir / "raw_mask.png",
        "labels": tmpdir / "labels.ass",
    }
    cv2.imwrite(str(paths["background"]), bg)
    cv2.imwrite(str(paths["after_mask"]), _rounded(sc.after[2], sc.after[3], sc.after_radius))
    cv2.imwrite(str(paths["raw_mask"]), _rounded(sc.raw[2], sc.raw[3], sc.raw_radius))
    label_size = 64 if sc.background != "black" else 46
    paths["labels"].write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pill,Inter Tight Medium,{PILL_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Label,Inter Tight ExtraBold,{label_size},{ass_color(sc.label_color)},&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,2,1,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n", encoding="utf-8")
    return paths
