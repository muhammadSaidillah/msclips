"""Editing styles: named looks applied when a clip is rendered.

Each style is a real set of render settings (caption typography, colour grade, zoom rhythm, framing and
layout) that the FFmpeg/libass renderer executes. The podcast styles are derived from the user's own
editing skills (podcast-editor-v1 … podcast-editor-animasi-10, podcast-clip-editor); only the parts that the
renderer can reproduce faithfully are implemented. Generated illustration/B-roll layers, sound effects and the
animated editor timeline from those skills are not part of these styles yet, and nothing here removes
watermarks from footage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CaptionSpec:
    layout: str = "line"  # "line": one wrapped block | "sandwich": small / BIG KEYWORD / small
    reveal: str = "all"  # "all": whole phrase shown, spoken word highlighted | "ghost": unspoken words dim | "appear": words appear as spoken
    font: str = "Inter ExtraBold"
    size: int = 84
    color: str = "#FFFFFF"
    current_color: str | None = None  # colour of the word being spoken (reveal "all")
    key_font: str | None = None  # keyword typography (None = same as font)
    key_size: int | None = None
    key_color: str | None = None
    key_box: str | None = None  # solid box behind the keyword line (sandwich layout)
    key_italic: bool = False
    key_upper: bool = False
    key_glow: bool = False
    emphasis_color: str | None = None  # a few strongest keywords per clip get this colour instead
    case: str = "keep"  # "keep" | "upper" | "lower"
    outline: int = 5
    shadow: int = 2
    y: float = 0.66  # vertical centre of the caption block, fraction of the frame height
    max_words: int = 4
    max_chars: int = 24
    pop: bool = False  # keyword scales in from 115%


@dataclass(frozen=True)
class Showcase:
    """Before/After presentation layout: the edited clip and the raw footage as cards on a background."""

    background: str  # "white" | "dark" | "black"
    after: tuple[int, int, int, int]  # x, y, w, h on the 1080x1920 canvas
    raw: tuple[int, int, int, int]
    after_radius: int
    raw_radius: int
    after_label: str
    raw_label: str
    label_kind: str  # "pill" | "text"
    raw_mono: bool  # raw card in black and white
    after_on_top: bool = True
    label_color: str = "#FFFFFF"
    landscape: bool = False  # cards are 16:9 (source must be landscape)


@dataclass(frozen=True)
class EditStyle:
    id: str
    name: str
    tagline: str
    source: str  # where the look comes from
    caption: CaptionSpec
    grade: str = "neutral"  # key in GRADES
    zoom: str = "none"  # "none" | "dynamic" (shot size changes every few seconds) | "punch" (zoom-in on keywords)
    framing: str = "track"  # "track": follow the speaker | "static": one crop at the speaker's median position
    grain: bool = False
    showcase: Showcase | None = None
    hook_fg: str = "#000000"
    hook_bg: str = "#FFFFFF"
    hook_font: str = "Inter ExtraBold"
    group: str = "podcast"  # "basic" | "podcast" | "showcase"
    omitted: tuple[str, ...] = field(default_factory=tuple)  # parts of the source skill not rendered yet

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("caption")
        d["showcase"] = self.showcase is not None
        d["omitted"] = list(self.omitted)
        return d


GRADES = {
    "neutral": "eq=contrast=1.03:saturation=1.03",
    "warm": "eq=contrast=1.05:saturation=0.95:brightness=0.01,colorbalance=rm=0.04:gm=0.01:bm=-0.04,vignette=angle=PI/6",
    "cinematic": "curves=all='0/0.04 0.25/0.22 0.75/0.79 1/0.97',eq=saturation=0.92,"
                 "colorbalance=rs=0.03:bs=-0.04:rh=0.03:bh=-0.03,vignette=angle=PI/5",
    "contrast": "eq=contrast=1.09:saturation=0.9:brightness=-0.02,vignette=angle=PI/6",
    "none": "",
}

_NO_LAYERS = "AI illustration / B-roll layers"
_NO_SFX = "sound effects"
_NO_TIMELINE = "animated editor timeline panel"

STYLES: dict[str, EditStyle] = {}


def _add(style: EditStyle) -> None:
    STYLES[style.id] = style


# --- Basic MSclips caption looks -------------------------------------------------------------------------
_add(EditStyle(
    "bold", "Bold", "Big uppercase captions, spoken word in yellow.", "MSclips",
    CaptionSpec(size=84, current_color="#FFE500", case="upper", outline=7, max_words=3, max_chars=22, y=0.62),
    group="basic"))
_add(EditStyle(
    "clean", "Clean", "Calm sentence-case captions, no highlight.", "MSclips",
    CaptionSpec(size=64, outline=4, max_words=7, max_chars=34, y=0.64), group="basic"))
_add(EditStyle(
    "karaoke", "Karaoke", "Phrase on screen, each word lights up as it is spoken.", "MSclips",
    CaptionSpec(size=74, current_color="#FFD145", outline=6, max_words=5, max_chars=28, y=0.63), group="basic"))

# --- From the user's podcast editing skills ---------------------------------------------------------------
_add(EditStyle(
    "reels-dinamis", "Reels Dinamis", "Subtitle per kata, kata kunci kuning menyala, zoom closeup ⇄ medium.",
    "podcast-editor-v1",
    CaptionSpec(font="Inter ExtraBold", size=76, key_color="#F9EC2F", key_glow=True, outline=5, y=0.68,
                max_words=4, max_chars=24),
    grade="warm", zoom="dynamic", omitted=(_NO_LAYERS,)))
_add(EditStyle(
    "kuning-putih", "Kuning Putih", "Putih kecil + kata kunci kuning tebal, kata belum diucap redup.",
    "podcast-editor-2",
    CaptionSpec(layout="sandwich", reveal="ghost", font="Inter Tight Medium", size=60,
                key_font="Inter ExtraBold", key_size=118, key_color="#EDE228", case="lower", outline=0, shadow=3,
                y=0.66, max_words=5, max_chars=28),
    grade="warm", zoom="dynamic", omitted=(_NO_LAYERS,)))
_add(EditStyle(
    "sinematik-lukis", "Sinematik Lukis", "Sans tebal lowercase + serif kecil, kata penekanan rose-merah, grade hangat.",
    "podcast-editor-3-horizontal",
    CaptionSpec(layout="sandwich", reveal="appear", font="Newsreader Medium Italic", size=58,
                key_font="Inter Tight ExtraBold", key_size=136, emphasis_color="#E8566A", case="lower",
                outline=0, shadow=3, y=0.66, max_words=5, max_chars=28),
    grade="cinematic", framing="static", grain=True, omitted=(_NO_LAYERS,)))
_add(EditStyle(
    "explainer", "Explainer", "Subtitle kondensed per kata, pernyataan kunci di kotak merah.",
    "podcast-editor-4",
    CaptionSpec(layout="sandwich", reveal="appear", font="Barlow Condensed SemiBold", size=70,
                key_font="Barlow Condensed ExtraBold", key_size=86, key_box="#E50000", case="lower",
                outline=0, shadow=3, y=0.66, max_words=5, max_chars=26),
    grade="contrast", framing="static", hook_fg="#FFFFFF", hook_bg="#E50000",
    omitted=(_NO_LAYERS, "glitch flash", _NO_SFX)))
_add(EditStyle(
    "sinematik-serif", "Sinematik Serif", "Bold lowercase + serif miring, kata muncul redup lalu tegas.",
    "podcast-editor-5",
    CaptionSpec(layout="sandwich", reveal="ghost", font="Newsreader Medium Italic", size=56,
                key_font="Inter Tight ExtraBold", key_size=124, case="lower", outline=0, shadow=3,
                y=0.67, max_words=5, max_chars=28),
    grade="cinematic", framing="static", grain=True, omitted=(_NO_LAYERS,)))
_add(EditStyle(
    "kinetic", "Kinetic Type", "Tiap kata jadi tipografi besar yang muncul saat diucapkan, angka merah.",
    "podcast-clip-editor",
    CaptionSpec(layout="sandwich", reveal="appear", font="Inter Tight Medium", size=58,
                key_font="Inter Tight ExtraBold", key_size=150, emphasis_color="#F2160C", case="lower",
                outline=0, shadow=3, y=0.66, max_words=4, max_chars=22, pop=True),
    grade="warm", zoom="dynamic", omitted=(_NO_LAYERS, "icons and infographics", _NO_SFX, "watermark")))

# --- Before/After showcase layouts (portfolio videos) -----------------------------------------------------
_add(EditStyle(
    "showcase-before-after", "Before / After", "Kartu Before mentah + After (grade hangat, subtitle kuning).",
    "podcast-editor-timeline-6",
    CaptionSpec(layout="sandwich", reveal="appear", font="Newsreader Medium", size=62,
                key_font="Inter Tight ExtraBold", key_size=124, key_color="#FFD43B", key_glow=True,
                key_upper=True, outline=0, shadow=3, y=0.66, max_words=5, max_chars=26, pop=True),
    grade="warm",
    showcase=Showcase("dark", after=(497, 470, 511, 909), raw=(72, 650, 410, 729), after_radius=28, raw_radius=24,
                      after_label="After", raw_label="Before", label_kind="text", raw_mono=False,
                      label_color="#FFD43B"),
    group="showcase", omitted=(_NO_LAYERS, _NO_TIMELINE)))
_add(EditStyle(
    "showcase-result", "Raw vs Result (putih)", "Latar putih, Raw B&W di belakang, Result dengan kata kunci kotak oranye.",
    "podcast-editor-timeline-7",
    CaptionSpec(layout="sandwich", reveal="appear", font="Inter Tight Medium", size=60,
                key_font="Inter Tight Black", key_size=104, key_box="#D9653B", case="lower", outline=0, shadow=3,
                y=0.70, max_words=5, max_chars=26),
    grade="warm",
    showcase=Showcase("white", after=(400, 440, 608, 1084), raw=(72, 760, 400, 711), after_radius=40, raw_radius=28,
                      after_label="Result", raw_label="Raw footage", label_kind="pill", raw_mono=True),
    group="showcase", omitted=(_NO_LAYERS, _NO_TIMELINE)))
_add(EditStyle(
    "showcase-169", "Asli vs Hasil 16:9 (hitam)", "Untuk video horizontal: asli B&W di atas, hasil 16:9 dengan serif miring di bawah.",
    "podcast-editor-timeline-8",
    CaptionSpec(layout="sandwich", reveal="appear", font="Inter Tight Medium", size=60,
                key_font="Newsreader Bold Italic", key_size=104, outline=0, shadow=3, y=0.40,
                max_words=5, max_chars=26),
    grade="warm", zoom="punch",
    showcase=Showcase("black", after=(60, 720, 960, 540), raw=(60, 140, 960, 540), after_radius=14, raw_radius=14,
                      after_label="After", raw_label="Original", label_kind="text", raw_mono=True, landscape=True),
    group="showcase", omitted=(_NO_LAYERS, _NO_TIMELINE)))
_add(EditStyle(
    "showcase-ungu", "Raw vs After (ungu)", "Latar putih, kata kunci KAPITAL miring ungu.",
    "podcast-editor-2screen-9",
    CaptionSpec(layout="sandwich", reveal="appear", font="Inter Tight Light", size=58,
                key_font="Inter Tight Black Italic", key_size=112, key_color="#9A63FF", key_italic=True,
                key_upper=True, outline=0, shadow=3, y=0.68, max_words=5, max_chars=26),
    grade="warm",
    showcase=Showcase("white", after=(383, 418, 608, 1084), raw=(94, 706, 400, 711), after_radius=34, raw_radius=24,
                      after_label="After", raw_label="Raw", label_kind="pill", raw_mono=True),
    group="showcase", omitted=("purple motion-graphic layers", "window light animation")))
_add(EditStyle(
    "showcase-gelap", "After / Before (gelap)", "Latar gelap, satu shot statis, tipografi bold + serif, kata rose.",
    "podcast-editor-animasi-10",
    CaptionSpec(layout="sandwich", reveal="appear", font="Newsreader Medium Italic", size=56,
                key_font="Inter Tight ExtraBold", key_size=124, emphasis_color="#F28A8A", case="lower",
                outline=0, shadow=3, y=0.70, max_words=5, max_chars=26),
    grade="warm", framing="static",
    showcase=Showcase("dark", after=(60, 520, 540, 960), raw=(624, 520, 400, 711), after_radius=26, raw_radius=22,
                      after_label="After", raw_label="Before", label_kind="text", raw_mono=False),
    group="showcase", omitted=("3 animated painted illustrations", _NO_TIMELINE)))


# --- Auto pick --------------------------------------------------------------------------------------------
# The clip-discovery step labels every clip with an editing_style and a category; map those to a look.
AUTO_BY_EDITING_STYLE = {
    "energetic": "reels-dinamis",
    "podcast": "kuning-putih",
    "storytelling": "sinematik-lukis",
    "educational": "explainer",
    "cinematic": "sinematik-serif",
    "comedy": "kinetic",
    "clean": "clean",
}
AUTO_BY_CATEGORY = {
    "tip": "explainer",
    "educational": "explainer",
    "story": "sinematik-lukis",
    "emotional": "sinematik-serif",
    "humor": "kinetic",
    "opinion": "reels-dinamis",
    "surprising": "reels-dinamis",
    "insight": "kuning-putih",
    "conclusion": "kuning-putih",
}
AUTO_DEFAULT = "kuning-putih"


def resolve_style(requested: str, editing_style: str | None, category: str | None, landscape_source: bool) -> tuple[EditStyle, str]:
    """Pick the style for one clip. Returns (style, reason)."""
    if requested == "auto":
        if editing_style in AUTO_BY_EDITING_STYLE:
            sid = AUTO_BY_EDITING_STYLE[editing_style]
            return STYLES[sid], f"auto: AI labelled this clip '{editing_style}'"
        if category in AUTO_BY_CATEGORY:
            sid = AUTO_BY_CATEGORY[category]
            return STYLES[sid], f"auto: clip category '{category}'"
        return STYLES[AUTO_DEFAULT], "auto: default podcast look"
    style = STYLES[requested]
    if style.showcase and style.showcase.landscape and not landscape_source:
        return STYLES["showcase-before-after"], f"{style.name} needs a horizontal source; used Before / After instead"
    return style, "chosen"


def catalog() -> list[dict]:
    return [s.to_json() for s in STYLES.values()]
