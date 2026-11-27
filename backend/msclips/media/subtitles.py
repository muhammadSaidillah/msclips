"""Build ASS subtitle files from word timestamps, in the typography of an editing style."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from msclips.media.styles import STYLES, CaptionSpec, EditStyle

PLAY_W, PLAY_H = 1080, 1920
HOOK_MARGIN_V = 250
SIDE_MARGIN = 90

# Function words never chosen as the phrase keyword (Indonesian + English).
STOPWORDS = set("""
yang dan di ke dari ini itu dengan untuk pada adalah atau juga karena jadi kalau kalo tapi tetapi sudah udah belum
akan bisa ada tidak nggak gak ga enggak aku saya kamu kita kami mereka dia ia lu lo gue gua nya pun lah kah dong sih
kok ya iya nah tuh deh loh kan aja saja lagi masih sangat banget lebih paling sama seperti kayak buat bagi oleh
the a an and or but of to in on at for with is are was were be been it this that these those i you we they he she
my your our their so if then than as by from just very really not no do does did have has had will would can could
""".split())


@dataclass
class Word:
    text: str
    start: float
    end: float


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def tag_color(hex_rgb: str) -> str:
    """Colour for an inline override tag, e.g. \\c&HBBGGRR&."""
    h = hex_rgb.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def clip_words(segments: list[dict], start: float, end: float) -> list[Word]:
    """Words inside [start, end], re-timed relative to the clip start."""
    out = []
    for seg in segments:
        for w in seg["words"]:
            if w["s"] >= start - 0.05 and w["e"] <= end + 0.05:
                out.append(Word(w["w"], max(0.0, w["s"] - start), min(end - start, w["e"] - start)))
    return out


def chunk_words(words: list[Word], max_chars: int, max_words: int) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        cur_len = sum(len(x.text) + 1 for x in cur)
        gap = w.start - cur[-1].end if cur else 0
        if cur and (len(cur) >= max_words or cur_len + len(w.text) > max_chars or gap > 0.6):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w.text) or (re.search(r"[,;:]$", w.text) and len(cur) >= 2):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def estimate_line_width(text: str, size: int) -> float:
    """Rough width in pixels for a bold sans font (used by QC to flag overflow)."""
    return sum(size * (0.36 if c == " " else 0.66 if c.isupper() else 0.56) for c in text)


def _clean(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def pick_keyword(chunk: list[Word], boost: set[str] | frozenset[str] = frozenset()) -> int:
    """Index of the phrase's keyword: the strongest content word, else the longest word."""
    best, best_score = 0, -1.0
    for i, w in enumerate(chunk):
        c = _clean(w.text)
        score = len(c) + (6 if c in boost else 0) + (4 if any(ch.isdigit() for ch in c) else 0)
        if c in STOPWORDS or (len(c) < 3 and not c.isdigit()):
            score -= 100
        if score > best_score:
            best, best_score = i, score
    return best


def _cased(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        # Keep acronyms (AI, CEO) as they are.
        return text if len(text) <= 4 and text.isupper() else text.lower()
    return text


def _strip_punct(text: str) -> str:
    return text.rstrip(",;:")


def build_ass(
    words: list[Word],
    style: str | EditStyle = "bold",
    hook: str | None = None,
    hook_duration: float = 3.0,
    play: tuple[int, int] = (PLAY_W, PLAY_H),
    boost: set[str] | None = None,
) -> tuple[str, list[tuple[str, int]]]:
    """Returns (ass document, [(caption line, font size)]) for QC."""
    st = STYLES[style] if isinstance(style, str) else style
    cs: CaptionSpec = st.caption
    pw, ph = play
    scale = pw / PLAY_W if pw < ph else ph / PLAY_W  # landscape (1920x1080): sizes are for the short side
    size = round(cs.size * scale)
    key_size = round((cs.key_size or cs.size) * scale)
    key_font = cs.key_font or cs.font
    side = round(SIDE_MARGIN * pw / PLAY_W)
    shadow_col = "&H64000000"
    box_pad = round(14 * scale)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {pw}
PlayResY: {ph}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{cs.font},{size},{ass_color(cs.color)},&H000000FF,&H00000000,{shadow_col},0,0,0,0,100,100,0,0,1,{cs.outline},{cs.shadow},5,{side},{side},0,1
Style: Key,{key_font},{key_size},{ass_color(cs.key_color or cs.color)},&H000000FF,&H00000000,{shadow_col},0,{1 if cs.key_italic else 0},0,0,100,100,0,0,1,{cs.outline},{cs.shadow},5,{side},{side},0,1
Style: KeyBox,{key_font},{key_size},{ass_color(cs.key_color or '#FFFFFF')},&H000000FF,{ass_color(cs.key_box or '#000000')},&H00000000,0,{1 if cs.key_italic else 0},0,0,100,100,0,0,3,{box_pad},0,5,{side},{side},0,1
Style: Hook,{st.hook_font},{round(70 * scale)},{ass_color(st.hook_fg)},&H000000FF,{ass_color(st.hook_bg)},{ass_color(st.hook_bg)},0,0,0,0,100,100,0,0,3,{round(18 * scale)},0,8,{side},{side},{round(HOOK_MARGIN_V * ph / PLAY_H)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    boost = {_clean(b) for b in (boost or set())}
    chunks = chunk_words(words, cs.max_chars, cs.max_words)
    keys = [pick_keyword(c, boost) for c in chunks]

    emphasis: set[int] = set()
    if cs.emphasis_color and chunks:
        ranked = sorted(range(len(chunks)), key=lambda i: (
            any(ch.isdigit() for ch in chunks[i][keys[i]].text), _clean(chunks[i][keys[i]].text) in boost,
            len(_clean(chunks[i][keys[i]].text))), reverse=True)
        n = max(1, round(len(chunks) / 5))
        emphasis = set(ranked[:n]) | {i for i in range(len(chunks)) if any(ch.isdigit() for ch in chunks[i][keys[i]].text)}

    cx = pw // 2
    cy = round(cs.y * ph)
    events: list[str] = []
    lines: list[tuple[str, int]] = []
    has_key_look = bool(cs.key_color or cs.key_font or cs.emphasis_color or cs.key_box or cs.layout == "sandwich")

    def vis(j: int, i: int) -> str:
        if j <= i:
            return ""
        return "\\alpha&H99&" if cs.reveal == "ghost" else "\\alpha&HFF&" if cs.reveal == "appear" else ""

    def key_overrides(ci: int, j: int, i: int, inline: bool) -> str:
        col = cs.emphasis_color if ci in emphasis else cs.key_color
        o = ""
        if inline:
            o += f"\\fn{key_font}\\fs{key_size}"
            if cs.key_italic:
                o += "\\i1"
        if col and not cs.key_box:
            o += f"\\c{tag_color(col)}"
            if cs.key_glow:
                o += f"\\3c{tag_color(col)}\\bord{max(2, round(3 * scale))}\\blur{round(9 * scale)}\\3a&H90&"
        if cs.pop and j == i:
            o += "\\fscx116\\fscy116\\t(0,150,\\fscx100\\fscy100)"
        return o

    for ci, chunk in enumerate(chunks):
        texts = [_cased(w.text, cs.case) for w in chunk]
        k = keys[ci]
        key_text = _strip_punct(texts[k].upper() if cs.key_upper else texts[k])
        c_start = chunk[0].start
        nxt = chunks[ci + 1][0].start if ci + 1 < len(chunks) else None
        c_end = chunk[-1].end
        if nxt is not None and 0 < nxt - c_end < 0.35:
            c_end = nxt  # avoid flicker between close chunks
        bounds = [w.start for w in chunk] + [c_end]
        bounds[0] = c_start

        if cs.layout == "line":
            lines.append((" ".join(texts), max(size, key_size) if has_key_look else size))
            if not has_key_look and cs.reveal == "all" and not cs.current_color:
                events.append(f"Dialogue: 0,{_ts(c_start)},{_ts(c_end)},Caption,,0,0,0,,{{\\an5\\pos({cx},{cy})}}{_esc(' '.join(texts))}")
                continue
            for i in range(len(chunk)):
                s, e = bounds[i], bounds[i + 1]
                if e - s < 0.01:
                    continue
                parts = []
                for j, t in enumerate(texts):
                    o = vis(j, i)
                    if j == k and has_key_look:
                        o += key_overrides(ci, j, i, inline=bool(cs.key_font))
                    if j == i and cs.current_color:
                        o += f"\\c{tag_color(cs.current_color)}"
                    parts.append(f"{{{o}}}{_esc(t)}{{\\r}}" if o else _esc(t))
                events.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Caption,,0,0,0,,{{\\an5\\pos({cx},{cy})}}{' '.join(parts)}")
            continue

        # Sandwich: small words above, the keyword big in the middle, small words below.
        pre, post = list(range(0, k)), list(range(k + 1, len(chunk)))
        gap = round((key_size + size) / 2 * 1.08) + (box_pad if cs.key_box else 0)
        y_pre, y_post = cy - gap, cy + gap
        if pre:
            lines.append((" ".join(texts[j] for j in pre), size))
        lines.append((key_text, key_size))
        if post:
            lines.append((" ".join(texts[j] for j in post), size))
        for i in range(len(chunk)):
            s, e = bounds[i], bounds[i + 1]
            if e - s < 0.01:
                continue
            for idxs, y in ((pre, y_pre), (post, y_post)):
                if not idxs or (cs.reveal == "appear" and idxs[0] > i):
                    continue
                parts = []
                for j in idxs:
                    o = vis(j, i)
                    if j == i and cs.current_color:
                        o += f"\\c{tag_color(cs.current_color)}"
                    parts.append(f"{{{o}}}{_esc(texts[j])}{{\\r}}" if o else _esc(texts[j]))
                events.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Caption,,0,0,0,,{{\\an5\\pos({cx},{y})}}{' '.join(parts)}")
            if cs.reveal == "appear" and i < k:
                continue
            o = vis(k, i) + key_overrides(ci, k, i, inline=False)
            style_name = "KeyBox" if cs.key_box else "Key"
            events.append(f"Dialogue: 1,{_ts(s)},{_ts(e)},{style_name},,0,0,0,,{{\\an5\\pos({cx},{cy}){o}}}{_esc(key_text)}")
    if hook:
        events.append(f"Dialogue: 2,{_ts(0)},{_ts(hook_duration)},Hook,,0,0,0,,{_esc(hook)}")
    return header + "\n".join(events) + "\n", lines


def write_ass(path: Path, *args, **kwargs) -> list[tuple[str, int]]:
    doc, lines = build_ass(*args, **kwargs)
    path.write_text(doc, encoding="utf-8")
    return lines
