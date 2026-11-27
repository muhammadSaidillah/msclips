"""End-to-end pipeline on a real speech video: real transcription (faster-whisper), real FFmpeg render + QC.

The Claude call is replaced with a deterministic stand-in that picks segments from the *actual*
transcript, so everything after the model's choice (boundary snapping, de-dup, render, QC) is real.
"""

import shutil

import pytest

from msclips.ai import discovery
from msclips.media.probe import probe
from msclips.storage import get_storage
from msclips.workers.pipeline import analyze, render_clip
from msclips.workers.tasks import probe_source
from tests.helpers import upload_file

pytestmark = pytest.mark.skipif(not shutil.which("espeak-ng"), reason="needs espeak-ng to synthesise speech")


def fake_claude_factory(calls):
    def fake(prompt: str):
        calls.append(prompt)
        lines = [ln for ln in prompt.splitlines() if ln.startswith("[")]
        n = len(lines)
        assert n >= 2, "transcript should have several segments"
        mid = n // 2
        res = discovery.DiscoveryResult(
            clips=[
                discovery.ProposedClip(
                    start_segment_id=0, end_segment_id=max(0, mid - 1), title="Pembukaan dan tips pertama",
                    hook="Tips pertama memulai bisnis", category="tip", reason="Tips jelas dan berdiri sendiri.",
                    scores=discovery.Scores(hook=7, emotion=4, value=8, standalone=8, retention=6, shareability=6),
                    confidence=0.7, editing_style="clean",
                ),
                discovery.ProposedClip(
                    start_segment_id=mid, end_segment_id=n - 1, title="Pisahkan keuangan",
                    hook="Alasan usaha kecil bangkrut", category="insight", reason="Insight praktis.",
                    scores=discovery.Scores(hook=8, emotion=5, value=9, standalone=7, retention=7, shareability=7),
                    confidence=0.8, editing_style="storytelling",
                ),
            ],
            notes="",
        )
        return res, "test-stand-in", {"input_tokens": 0, "output_tokens": 0}

    return fake


async def _ready_project(client, media_dir):
    res = await upload_file(client, media_dir / "talk.mp4")
    assert await probe_source({}, res["job"]["id"]) == "succeeded"
    return res["project_id"]


async def test_analysis_requires_api_key_and_says_so(client, media_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    pid = await _ready_project(client, media_dir)
    r = await client.post(f"/projects/{pid}/analysis", json={"clip_count": 2, "min_duration_s": 5,
                                                              "max_duration_s": 30, "language": "id"})
    assert r.status_code == 202, r.text
    job_id = r.json()["job"]["id"]
    assert await analyze({}, job_id) == "failed"
    st = (await client.get(f"/projects/{pid}/analysis")).json()
    assert st["run"]["status"] == "failed"
    assert "ANTHROPIC_API_KEY" in st["run"]["error"]
    assert st["candidates"] == []
    # transcription still happened and is kept for the retry
    assert st["transcript"]["word_count"] > 10 and st["transcript"]["language"] == "id"


async def test_full_pipeline_transcribe_discover_render_qc(client, media_dir, monkeypatch, fake_queue):
    calls: list[str] = []
    monkeypatch.setattr(discovery, "call_claude", fake_claude_factory(calls))
    pid = await _ready_project(client, media_dir)

    r = await client.post(f"/projects/{pid}/analysis", json={"clip_count": 2, "min_duration_s": 5,
                                                              "max_duration_s": 40, "language": "id"})
    assert r.status_code == 202
    assert (await client.post(f"/projects/{pid}/analysis", json={"clip_count": 2})).status_code == 409
    assert await analyze({}, r.json()["job"]["id"]) == "succeeded"

    st = (await client.get(f"/projects/{pid}/analysis")).json()
    assert st["run"]["status"] == "succeeded" and st["job"]["progress"] == 1.0
    assert "Find the" in calls[0] and "[0]" in calls[0]  # the model saw the real transcript
    cands = st["candidates"]
    assert len(cands) == 2
    for c in cands:
        assert 0 <= c["start_s"] < c["end_s"]
        assert c["transcript_text"]
        assert 0 <= c["score"] <= 100
    assert cands[0]["end_s"] <= cands[1]["start_s"] + 0.2

    # reject + select toggles
    r = await client.patch(f"/candidates/{cands[1]['id']}", json={"status": "rejected"})
    assert r.json()["status"] == "rejected"

    r = await client.post(f"/projects/{pid}/renders",
                          json={"candidate_ids": [c["id"] for c in cands], "edit_style": "auto"})
    assert r.status_code == 202 and len(r.json()) == 2
    renders = r.json()
    r = await client.post(f"/projects/{pid}/renders",
                          json={"candidate_ids": [cands[0]["id"]], "edit_style": "showcase-ungu"})
    assert r.status_code == 202
    renders += r.json()
    bad = await client.post(f"/projects/{pid}/renders", json={"candidate_ids": [cands[0]["id"]], "edit_style": "nope"})
    assert bad.status_code == 422
    for rd in renders:
        assert rd["status"] == "queued"
        # no download before the render exists
        assert (await client.get(f"/renders/{rd['id']}/file")).status_code == 409
        assert await render_clip({}, rd["job"]["id"]) == "succeeded"

    out = (await client.get(f"/projects/{pid}/renders")).json()
    assert {o["status"] for o in out} == {"succeeded"}
    for o in out:
        assert o["qc"]["status"] in ("pass", "warn")
        names = {c["name"]: c["status"] for c in o["qc"]["checks"]}
        for must_pass in ("file", "resolution", "codec", "frame_rate", "duration", "audio"):
            assert names[must_pass] == "pass", o["qc"]
        assert o["crop"]["mode"] == "center"  # synthetic video has no face
        assert o["settings"]["resolved_style"]
        assert o["file_size_bytes"] > 10_000
    assert {o["settings"]["resolved_style"] for o in out} == {"clean", "sinematik-lukis", "showcase-ungu"}

    # The stored file really is a 1080x1920 H.264/AAC clip of the right length.
    first = out[-1]
    r = await client.get(f"/renders/{first['id']}/file", params={"download": True})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    tmp = get_storage().root / "check.mp4"
    tmp.write_bytes(r.content)
    info = await probe(tmp)
    assert (info.width, info.height, info.video_codec, info.audio_codec) == (1080, 1920, "h264", "aac")
    assert abs(info.duration_s - first["duration_s"]) < 0.25
    tmp.unlink()

    z = await client.get(f"/projects/{pid}/renders.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"


async def test_analysis_rejects_unready_or_invalid(client, media_dir):
    res = await upload_file(client, media_dir / "talk.mp4")  # not probed yet -> processing
    r = await client.post(f"/projects/{res['project_id']}/analysis", json={"clip_count": 3})
    assert r.status_code == 409
    await probe_source({}, res["job"]["id"])
    r = await client.post(f"/projects/{res['project_id']}/analysis",
                          json={"clip_count": 3, "min_duration_s": 60, "max_duration_s": 30})
    assert r.status_code == 422
    r = await client.post(f"/projects/{res['project_id']}/analysis", json={"clip_count": 0})
    assert r.status_code == 422
