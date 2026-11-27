from pathlib import Path


async def upload_file(client, path: Path, *, content_type: str = "video/mp4", complete: bool = True, name=None):
    data = path.read_bytes()
    r = await client.post(
        "/uploads",
        json={"filename": path.name, "size_bytes": len(data), "content_type": content_type, "project_name": name},
    )
    assert r.status_code == 201, r.text
    up = r.json()["upload"]
    cs = up["chunk_size"]
    for i in range(up["total_chunks"]):
        rr = await client.put(f"/uploads/{up['id']}/chunks/{i}", content=data[i * cs : (i + 1) * cs])
        assert rr.status_code == 200, rr.text
    result = {"upload": up, "project_id": up["project_id"]}
    if complete:
        rc = await client.post(f"/uploads/{up['id']}/complete")
        assert rc.status_code == 200, rc.text
        result["job"] = rc.json()["job"]
    return result
