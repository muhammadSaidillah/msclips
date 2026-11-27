from pathlib import Path

from msclips.core.config import get_settings
from msclips.workers.tasks import probe_source
from tests.helpers import upload_file


async def run_job(job_id: str) -> str:
    return await probe_source({}, job_id)


async def test_full_upload_and_metadata(client, fake_queue, media_dir):
    res = await upload_file(client, media_dir / "landscape.mp4", name="Podcast ep 1")
    pid = res["project_id"]
    assert res["upload"]["total_chunks"] > 1  # exercised multi-chunk path
    assert fake_queue.enqueued and fake_queue.enqueued[-1][0] == "probe_source"

    # Before the worker runs, the project must NOT claim to be ready.
    p = (await client.get(f"/projects/{pid}")).json()
    assert p["status"] == "processing"
    assert p["metadata"] is None

    assert await run_job(res["job"]["id"]) == "succeeded"

    p = (await client.get(f"/projects/{pid}")).json()
    assert p["status"] == "ready"
    assert p["name"] == "Podcast ep 1"
    m = p["metadata"]
    assert (m["display_width"], m["display_height"]) == (1280, 720)
    assert m["aspect_ratio"] == "16:9" and m["orientation"] == "landscape"
    assert abs(m["fps"] - 30) < 0.01
    assert 3.9 < m["duration_s"] < 4.2
    assert m["has_audio"] and m["audio_channels"] == 2 and m["audio_sample_rate"] == 48000
    assert p["source"]["sha256"] and len(p["source"]["sha256"]) == 64
    assert p["source"]["size_bytes"] == (media_dir / "landscape.mp4").stat().st_size
    assert p["has_thumbnail"]
    job = p["jobs"][0]
    assert job["status"] == "succeeded" and job["progress"] == 1.0 and job["attempts"] == 1

    # Staging file removed after ingest; stored file is byte-identical.
    assert not Path(res["upload"]["id"]).exists()
    staging = get_settings().staging_dir / f"{res['upload']['id']}.part"
    assert not staging.exists()

    r = await client.get(f"/projects/{pid}/source")
    assert r.status_code == 200 and r.content == (media_dir / "landscape.mp4").read_bytes()
    r = await client.get(f"/projects/{pid}/source", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    t = await client.get(f"/projects/{pid}/thumbnail")
    assert t.status_code == 200 and t.content[:3] == b"\xff\xd8\xff"

    dash = (await client.get("/dashboard")).json()
    assert dash["project_counts"]["ready"] >= 1
    assert dash["total_source_bytes"] >= p["source"]["size_bytes"]


async def test_portrait_without_audio(client, media_dir):
    res = await upload_file(client, media_dir / "portrait_noaudio.mov", content_type="video/quicktime")
    assert await run_job(res["job"]["id"]) == "succeeded"
    m = (await client.get(f"/projects/{res['project_id']}")).json()["metadata"]
    assert m["aspect_ratio"] == "9:16" and m["orientation"] == "portrait"
    assert m["has_audio"] is False and m["audio_track_count"] == 0
    assert abs(m["fps"] - 25) < 0.01


async def test_corrupt_file_fails_clearly(client, media_dir):
    res = await upload_file(client, media_dir / "corrupt.mp4")
    assert await run_job(res["job"]["id"]) == "failed"
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert p["status"] == "failed"
    assert "could not be read as a video" in p["status_message"]
    assert p["jobs"][0]["status"] == "failed" and p["jobs"][0]["attempts"] == 1  # deterministic: no retries
    assert p["metadata"] is None


async def test_audio_only_rejected(client, media_dir):
    res = await upload_file(client, media_dir / "audio_only.mp4")
    assert await run_job(res["job"]["id"]) == "failed"
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert "No video stream" in p["status_message"]


async def test_reprocess_after_success(client, media_dir, fake_queue):
    res = await upload_file(client, media_dir / "portrait_noaudio.mov")
    await run_job(res["job"]["id"])
    r = await client.post(f"/projects/{res['project_id']}/reprocess")
    assert r.status_code == 202
    assert await run_job(r.json()["id"]) == "succeeded"
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert p["status"] == "ready" and len(p["jobs"]) == 2


async def test_validation_rejects_bad_requests(client):
    r = await client.post("/uploads", json={"filename": "notes.txt", "size_bytes": 10})
    assert r.status_code == 422 and "Unsupported file type" in r.text
    r = await client.post("/uploads", json={"filename": "a.mp4", "size_bytes": 10, "content_type": "image/png"})
    assert r.status_code == 422
    r = await client.post("/uploads", json={"filename": "a.mp4", "size_bytes": 10**15})
    assert r.status_code == 413
    r = await client.post("/uploads", json={"filename": "a.mp4", "size_bytes": 0})
    assert r.status_code == 422


async def test_chunk_rules_resume_and_idempotency(client, media_dir):
    data = (media_dir / "landscape.mp4").read_bytes()
    up = (await client.post("/uploads", json={"filename": "x.mp4", "size_bytes": len(data)})).json()["upload"]
    cs, n = up["chunk_size"], up["total_chunks"]
    # wrong size
    r = await client.put(f"/uploads/{up['id']}/chunks/0", content=data[: cs - 1])
    assert r.status_code == 422
    # out of range
    r = await client.put(f"/uploads/{up['id']}/chunks/{n}", content=b"x")
    assert r.status_code == 422
    # send chunk 0 twice -> counted once
    for _ in range(2):
        r = await client.put(f"/uploads/{up['id']}/chunks/0", content=data[:cs])
    assert r.json()["received_chunks"] == [0] and r.json()["received_bytes"] == cs
    # complete with missing chunks is refused and lists them
    r = await client.post(f"/uploads/{up['id']}/complete")
    assert r.status_code == 409 and r.json()["detail"]["missing_chunks"][0] == 1
    # resume: status tells the client what is left; send the rest in reverse order
    status = (await client.get(f"/uploads/{up['id']}")).json()
    for i in sorted(set(range(n)) - set(status["received_chunks"]), reverse=True):
        await client.put(f"/uploads/{up['id']}/chunks/{i}", content=data[i * cs : (i + 1) * cs])
    r = await client.post(f"/uploads/{up['id']}/complete")
    assert r.status_code == 200
    staged = Path(get_settings().staging_dir / f"{up['id']}.part").read_bytes()
    assert staged == data
    # double complete refused
    assert (await client.post(f"/uploads/{up['id']}/complete")).status_code == 409


async def test_cancel_upload(client, media_dir):
    res = await upload_file(client, media_dir / "landscape.mp4", complete=False)
    up_id = res["upload"]["id"]
    r = await client.delete(f"/uploads/{up_id}")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert not (get_settings().staging_dir / f"{up_id}.part").exists()
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert p["status"] == "cancelled"
    assert (await client.put(f"/uploads/{up_id}/chunks/0", content=b"x")).status_code == 409


async def test_queue_down_marks_failure_visibly(client, fake_queue, media_dir):
    fake_queue.fail = True
    res = await upload_file(client, media_dir / "portrait_noaudio.mov")
    assert res["job"]["status"] == "failed"
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert p["status"] == "failed" and "queue unavailable" in p["status_message"]
    # recover: the staged file is kept, so retry processing works once the queue is back
    fake_queue.fail = False
    r = await client.post(f"/projects/{res['project_id']}/reprocess")
    assert r.status_code == 202
    assert await run_job(r.json()["id"]) == "succeeded"


async def test_cancel_queued_job(client, media_dir):
    res = await upload_file(client, media_dir / "portrait_noaudio.mov")
    r = await client.post(f"/jobs/{res['job']['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert await run_job(res["job"]["id"]) == "cancelled"  # worker skips it


async def test_list_search_rename_delete(client, media_dir):
    res = await upload_file(client, media_dir / "portrait_noaudio.mov", name="Unique Searchable Name")
    await run_job(res["job"]["id"])
    pid = res["project_id"]
    lst = (await client.get("/projects", params={"q": "searchable"})).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == pid
    lst = (await client.get("/projects", params={"status": "ready"})).json()
    assert all(i["status"] == "ready" for i in lst["items"])
    r = await client.patch(f"/projects/{pid}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed"
    stored = get_settings().storage_dir / "projects" / pid
    assert any(stored.iterdir())
    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    assert (await client.get(f"/projects/{pid}")).status_code == 404
    assert not any(stored.iterdir())


async def test_health(client):
    r = await client.get("/health")
    body = r.json()
    assert body["checks"]["database"]["ok"] and body["checks"]["ffmpeg"]["ok"] and body["checks"]["storage"]["ok"]


async def test_transient_failure_retries_then_succeeds(client, media_dir, monkeypatch):
    import pytest
    from arq import Retry

    from msclips.storage import get_storage

    storage = get_storage()
    real_put = storage.put_file
    calls = {"n": 0}

    async def flaky_put(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("storage temporarily unreachable")
        return await real_put(*a, **kw)

    monkeypatch.setattr(storage, "put_file", flaky_put)
    res = await upload_file(client, media_dir / "portrait_noaudio.mov")
    with pytest.raises(Retry):
        await run_job(res["job"]["id"])
    job = (await client.get(f"/jobs/{res['job']['id']}")).json()
    assert job["status"] == "queued" and "temporarily unreachable" in job["error"]
    p = (await client.get(f"/projects/{res['project_id']}")).json()
    assert p["status"] == "processing"  # not falsely failed, not falsely ready
    assert await run_job(res["job"]["id"]) == "succeeded"
    job = (await client.get(f"/jobs/{res['job']['id']}")).json()
    assert job["attempts"] == 2 and job["status"] == "succeeded"
