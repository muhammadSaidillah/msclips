"""Unit tests for boundary snapping, scoring, de-duplication, captions and framing (no I/O)."""

from msclips.ai.discovery import (
    DiscoveryResult,
    ProposedClip,
    Scores,
    build_prompt,
    postprocess,
    snap_boundaries,
    weighted_score,
)
from msclips.media.reframe import CropPlan, Shot, plan_shots
from msclips.media.subtitles import Word, build_ass, chunk_words, clip_words


def seg(i, start, words_text, step=0.4):
    words, t = [], start
    for w in words_text.split():
        words.append({"w": w, "s": round(t, 3), "e": round(t + step - 0.05, 3), "p": 0.9})
        t += step
    return {"id": i, "start": start, "end": words[-1]["e"], "text": words_text, "words": words}


SEGS = [
    seg(0, 0.0, "Halo semua selamat datang."),
    seg(1, 2.0, "Tips pertama kenali pelanggan kamu"),
    seg(2, 4.5, "sebelum menjual apa pun."),
    seg(3, 6.5, "Tips kedua pisahkan uang pribadi dan usaha."),
    seg(4, 10.0, "Itu alasan banyak usaha bangkrut."),
    seg(5, 13.0, "Terima kasih sudah mendengarkan."),
]


def clip(a, b, title="t", hook=8):
    return ProposedClip(
        start_segment_id=a, end_segment_id=b, title=title, hook="h", category="tip", reason="r",
        scores=Scores(hook=hook, emotion=5, value=7, standalone=8, retention=6, shareability=5),
        confidence=0.8, editing_style="clean",
    )


def test_snap_extends_to_sentence_end_and_pads_without_bleeding():
    start, end, text = snap_boundaries(SEGS, 1, 1, 2, 20, 15.0)
    # segment 1 has no sentence end, so it extends through segment 2 ("...apa pun.")
    assert text.endswith("pun.")
    assert start >= SEGS[0]["words"][-1]["e"]  # never cuts into the previous word
    assert start <= SEGS[1]["words"][0]["s"]
    assert end >= SEGS[2]["words"][-1]["e"]
    assert end <= SEGS[3]["words"][0]["s"]


def test_snap_rejects_invalid_ranges_and_too_short():
    assert snap_boundaries(SEGS, 3, 1, 2, 20, 15) is None
    assert snap_boundaries(SEGS, 0, 99, 2, 20, 15) is None
    assert snap_boundaries(SEGS, 0, 0, 30, 60, 15) is None  # far below min duration


def test_snap_trims_overlong_range_at_sentence_end():
    start, end, text = snap_boundaries(SEGS, 0, 5, 2, 8, 15.0)
    assert end - start <= 8 * 1.1 + 0.4
    assert text[-1] in ".!?"


def test_postprocess_dedupes_overlaps_and_ranks():
    res = DiscoveryResult(clips=[clip(1, 2, "a"), clip(1, 3, "overlap"), clip(3, 4, "b")], notes="")
    out = postprocess(res, SEGS, 5, 2, 20, 15.0)
    assert [c.title for c in out] == ["a", "b"]
    assert [c.rank for c in out] == [1, 2]
    assert out[0].start_s < out[0].end_s <= out[1].start_s + 0.2  # only shared silence padding


def test_postprocess_respects_requested_count():
    res = DiscoveryResult(clips=[clip(0, 0, "a"), clip(1, 2, "b"), clip(3, 3, "c")], notes="")
    assert len(postprocess(res, SEGS, 1, 1, 20, 15.0)) == 1


def test_weighted_score_bounds():
    assert weighted_score({k: 10 for k in ("hook", "emotion", "value", "standalone", "retention", "shareability")}) == 100
    assert weighted_score({"hook": 99}) <= 100


def test_prompt_contains_ids_and_times():
    p = build_prompt(SEGS, 3, 20, 60, "id")
    assert "[3] 00:06.5" in p and "Find the 3 best clips" in p


def test_captions_chunk_and_highlight():
    words = clip_words(SEGS, 2.0, 6.0)
    assert words[0].text == "Tips" and words[0].start == 0.0
    chunks = chunk_words(words, 22, 3)
    assert all(len(c) <= 3 for c in chunks)
    doc, lines = build_ass(words, style="bold", hook="Kenali pelanggan")
    assert "PlayResY: 1920" in doc and "Style: Caption" in doc
    assert "\\c&H00E5FF&" in doc  # current-word highlight
    assert "0:00:00.00,0:00:03.00,Hook," in doc
    assert lines[0][0] == lines[0][0].upper() and lines[0][1] == 84


def test_captions_escape_braces():
    doc, _ = build_ass([Word("{x}", 0, 1)], style="clean")
    assert "{x}" not in doc.split("[Events]")[1]


def test_plan_shots_holds_still_then_cuts():
    track = [(i / 2, 0.30) for i in range(10)] + [(5 + i / 2, 0.70) for i in range(10)]
    shots = plan_shots(track, 10.0)
    assert len(shots) == 2
    assert abs(shots[0].center_x - 0.30) < 0.02 and abs(shots[1].center_x - 0.70) < 0.02
    # small jitter does not move the crop
    jitter = [(i / 2, 0.5 + (0.03 if i % 2 else -0.03)) for i in range(20)]
    assert len(plan_shots(jitter, 10.0)) == 1


def test_crop_expression_and_clamping():
    plan = CropPlan("face", 1920, 1080, 608, 1080, shots=[Shot(0, 4, 0.0), Shot(4, 8, 0.99)])
    assert plan.x_for(0.0) == 0 and plan.x_for(0.99) == 1920 - 608
    assert plan.ffmpeg_crop_x() == "if(lt(t\\,4.000)\\,0\\,1312)"
