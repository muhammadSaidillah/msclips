from pathlib import Path

from msclips.media.reframe import CropPlan, Shot
from msclips.media.render import build_filtergraph, static_plan, zoom_filter, zoom_schedule
from msclips.media.showcase import make_assets
from msclips.media.styles import STYLES, resolve_style
from msclips.media.subtitles import Word, build_ass, pick_keyword

WORDS = [Word(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(
    "jadi kalau kita mau pelanggan setia kita harus kenali mereka. lima tahun lalu saya mulai usaha kecil "
    "dan ternyata 90 persen pelanggan datang dari rekomendasi teman".split())]
FONTS = Path(__file__).resolve().parent.parent / "msclips" / "assets" / "fonts"


def test_every_style_font_is_bundled():
    import subprocess

    names = set()
    for f in FONTS.iterdir():
        out = subprocess.run(["fc-scan", "--format", "%{fullname}\n", str(f)], capture_output=True, text=True).stdout
        names |= {n.strip() for n in out.replace(",", "\n").splitlines() if n.strip()}
    for s in STYLES.values():
        for font in {s.caption.font, s.caption.key_font or s.caption.font, s.hook_font}:
            assert font in names, f"{s.id}: font {font!r} not bundled"


def test_auto_pick_uses_ai_labels():
    assert resolve_style("auto", "educational", "tip", False)[0].id == "explainer"
    assert resolve_style("auto", None, "humor", False)[0].id == "kinetic"
    assert resolve_style("auto", None, None, False)[0].id == "kuning-putih"
    assert resolve_style("kinetic", "clean", "tip", False)[0].id == "kinetic"
    # 16:9 showcase falls back for vertical sources
    style, reason = resolve_style("showcase-169", None, None, landscape_source=False)
    assert style.id == "showcase-before-after" and "horizontal" in reason


def test_keyword_skips_function_words():
    chunk = [Word("jadi", 0, 1), Word("kalau", 1, 2), Word("pelanggan", 2, 3), Word("itu", 3, 4)]
    assert pick_keyword(chunk) == 2
    assert pick_keyword([Word("90", 0, 1), Word("persen", 1, 2)]) == 0  # numbers win


def test_sandwich_captions_reveal_words_as_spoken():
    doc, lines = build_ass(WORDS, style="explainer")
    events = doc.split("[Events]")[1]
    assert "KeyBox" in events and "Barlow Condensed SemiBold" in doc
    assert all(size in (70, 86) for _, size in lines)
    # The first keyword is not on screen before it is spoken
    first_key = next(ln for ln in events.splitlines() if ",KeyBox," in ln)
    assert first_key.startswith("Dialogue: 1,0:00:00.") is False or "pelanggan" not in first_key


def test_ghost_and_emphasis():
    doc, _ = build_ass(WORDS, style="kuning-putih")
    assert "\\alpha&H99&" in doc  # unspoken words dimmed
    doc, _ = build_ass(WORDS, style="kinetic")
    assert "\\c&H0C16F2&" in doc  # number keyword in the accent red
    assert "\\fscx116" in doc  # pop-in


def test_zoom_schedules():
    dyn = zoom_schedule("dynamic", WORDS, 12.0)
    assert len(dyn) >= 3 and all(1.0 <= z <= 1.35 for _, z in dyn)
    gaps = [b[0] - a[0] for a, b in zip(dyn, dyn[1:])]
    assert min(gaps) >= 1.7
    punch = zoom_schedule("punch", WORDS, 12.0)
    assert any(z > 1.0 for _, z in punch) and punch[-1][1] == 1.0
    assert zoom_filter([(0.0, 1.0)], 1080, 1920) == ""
    assert "if(lt(it,2.0),1.0,1.22)" in zoom_filter([(0.0, 1.0), (2.0, 1.22)], 1080, 1920)


def test_static_framing_uses_median_speaker_position():
    plan = CropPlan("face", 1920, 1080, 608, 1080, shots=[Shot(0, 8, 0.3), Shot(8, 10, 0.7)])
    assert static_plan(plan, 10).shots == [Shot(0.0, 10, 0.3)]


def test_showcase_graph_and_assets(tmp_path):
    style = STYLES["showcase-result"]
    assets = make_assets(style.showcase, tmp_path)
    assert all(p.exists() and p.stat().st_size > 0 for p in assets.values())
    plan = CropPlan("center", 1920, 1080, 608, 1080)
    g = build_filtergraph(plan, tmp_path / "c.ass", 10.0, style, [(0.0, 1.0)], assets)
    assert "alphamerge" in g and "hue=s=0" in g and "overlay=400:440" in g
