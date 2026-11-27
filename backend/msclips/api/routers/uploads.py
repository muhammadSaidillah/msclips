"""Resumable chunked upload.

Flow: POST /uploads -> PUT /uploads/{id}/chunks/{i} (any order, retry-safe) -> POST /uploads/{id}/complete.
`complete` only verifies and enqueues; hashing, storing and probing run in the worker.
"""

import asyncio
import math
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.api.projects_query import summaries
from msclips.api.schemas import CompleteOut, JobOut, UploadCreate, UploadOut, UploadStarted
from msclips.core.config import get_settings
from msclips.core.db import get_session
from msclips.core.users import current_user
from msclips.models import Job, JobStatus, JobType, Project, ProjectStatus, UploadSession, UploadStatus, User
from msclips.workers.queue import Queue, get_queue

router = APIRouter(prefix="/uploads", tags=["uploads"])


async def _owned_upload(upload_id: uuid.UUID, session: AsyncSession, user: User) -> UploadSession:
    upload = await session.get(UploadSession, upload_id, populate_existing=True)
    if upload is None:
        raise HTTPException(404, "Upload not found")
    project = await session.get(Project, upload.project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(404, "Upload not found")
    return upload


def _clean_filename(name: str) -> str:
    name = Path(name.replace("\\", "/")).name.strip()
    return "".join(c for c in name if c.isprintable())[:500] or "video"


@router.post("", response_model=UploadStarted, status_code=201)
async def create_upload(
    body: UploadCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    s = get_settings()
    filename = _clean_filename(body.filename)
    ext = Path(filename).suffix.lower()
    if ext not in s.allowed_extensions:
        raise HTTPException(
            422, f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(s.allowed_extensions)}"
        )
    if body.content_type and not (
        body.content_type.startswith("video/") or body.content_type in ("application/octet-stream", "")
    ):
        raise HTTPException(422, f"Content type '{body.content_type}' is not a video type.")
    if body.size_bytes > s.max_upload_bytes:
        raise HTTPException(
            413, f"File is {body.size_bytes / 1024**3:.2f} GiB; the limit is {s.max_upload_bytes / 1024**3:.0f} GiB."
        )

    name = (body.project_name or "").strip() or Path(filename).stem[:200]
    project = Project(owner_id=user.id, name=name, status=ProjectStatus.uploading)
    session.add(project)
    await session.flush()

    s.staging_dir.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4()
    staging = (s.staging_dir / f"{upload_id}.part").resolve()
    # Pre-size the staging file so chunks can be written at their offsets in any order.
    with open(staging, "wb") as f:
        f.truncate(body.size_bytes)

    upload = UploadSession(
        id=upload_id,
        project_id=project.id,
        filename=filename,
        content_type=body.content_type or None,
        size_bytes=body.size_bytes,
        chunk_size=s.chunk_size_bytes,
        total_chunks=max(1, math.ceil(body.size_bytes / s.chunk_size_bytes)),
        received_chunks=[],
        received_bytes=0,
        status=UploadStatus.active,
        staging_path=str(staging),
    )
    session.add(upload)
    await session.commit()
    await session.refresh(project)
    (summary,) = await summaries(session, [project])
    return UploadStarted(upload=UploadOut.model_validate(upload), project=summary)


@router.get("/{upload_id}", response_model=UploadOut)
async def get_upload(
    upload_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)
):
    return await _owned_upload(upload_id, session, user)


def _write_at(path: str, offset: int, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY)
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            written += os.pwrite(fd, view[written:], offset + written)
        os.fsync(fd)
    finally:
        os.close(fd)


@router.put("/{upload_id}/chunks/{index}", response_model=UploadOut)
async def put_chunk(
    upload_id: uuid.UUID,
    index: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    upload = await _owned_upload(upload_id, session, user)
    if upload.status != UploadStatus.active:
        raise HTTPException(409, f"Upload is {upload.status.value}; chunks are no longer accepted.")
    if not 0 <= index < upload.total_chunks:
        raise HTTPException(422, f"Chunk index {index} out of range 0..{upload.total_chunks - 1}")
    offset = index * upload.chunk_size
    expected = min(upload.chunk_size, upload.size_bytes - offset)

    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > expected:
            raise HTTPException(422, f"Chunk {index} is larger than expected {expected} bytes.")
    if len(data) != expected:
        raise HTTPException(422, f"Chunk {index} has {len(data)} bytes; expected {expected}.")

    if not Path(upload.staging_path).exists():
        raise HTTPException(409, "Staging file missing; the upload was cancelled or cleaned up.")
    await asyncio.to_thread(_write_at, upload.staging_path, offset, bytes(data))

    # Atomic, idempotent bookkeeping: re-sending a chunk never double-counts.
    await session.execute(
        text(
            "UPDATE upload_sessions SET received_chunks = array_append(received_chunks, :i), "
            "received_bytes = received_bytes + :n, updated_at = now() "
            "WHERE id = :id AND status = 'active' AND NOT (:i = ANY(received_chunks))"
        ),
        {"i": index, "n": expected, "id": upload.id},
    )
    await session.commit()
    return await _owned_upload(upload_id, session, user)


@router.post("/{upload_id}/complete", response_model=CompleteOut)
async def complete_upload(
    upload_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    queue: Queue = Depends(get_queue),
):
    upload = await _owned_upload(upload_id, session, user)
    if upload.status != UploadStatus.active:
        raise HTTPException(409, f"Upload is already {upload.status.value}.")
    missing = sorted(set(range(upload.total_chunks)) - set(upload.received_chunks))
    if missing:
        raise HTTPException(
            409, {"message": f"{len(missing)} chunk(s) missing", "missing_chunks": missing[:1000]}
        )
    staging = Path(upload.staging_path)
    if not staging.is_file() or staging.stat().st_size != upload.size_bytes:
        raise HTTPException(409, "Staged file is missing or has the wrong size. Please upload again.")

    res = await session.execute(
        update(UploadSession)
        .where(UploadSession.id == upload.id, UploadSession.status == UploadStatus.active)
        .values(status=UploadStatus.completed, completed_at=text("now()"))
    )
    if res.rowcount != 1:
        raise HTTPException(409, "Upload was completed or cancelled concurrently.")
    job = Job(project_id=upload.project_id, type=JobType.probe_source, payload={"upload_id": str(upload.id)})
    session.add(job)
    await session.execute(
        update(Project)
        .where(Project.id == upload.project_id)
        .values(status=ProjectStatus.processing, status_message="Queued for metadata extraction")
    )
    await session.commit()
    try:
        job.arq_job_id = await queue.enqueue_job_task("probe_source", job.id)
        await session.commit()
    except Exception as e:  # queue down: leave a visible, retryable failure instead of a stuck job
        await session.rollback()
        msg = f"Could not queue processing (job queue unavailable: {e}). Use 'Retry processing'."
        await session.execute(update(Job).where(Job.id == job.id).values(status=JobStatus.failed, error=msg))
        await session.execute(
            update(Project).where(Project.id == upload.project_id).values(status=ProjectStatus.failed, status_message=msg)
        )
        await session.commit()
    await session.refresh(job)
    upload = await _owned_upload(upload_id, session, user)
    return CompleteOut(upload=UploadOut.model_validate(upload), job=JobOut.model_validate(job))


@router.delete("/{upload_id}", response_model=UploadOut)
async def cancel_upload(
    upload_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)
):
    upload = await _owned_upload(upload_id, session, user)
    if upload.status != UploadStatus.active:
        raise HTTPException(409, f"Upload is {upload.status.value} and cannot be cancelled.")
    await session.execute(
        update(UploadSession).where(UploadSession.id == upload.id).values(status=UploadStatus.cancelled)
    )
    await session.execute(
        update(Project)
        .where(Project.id == upload.project_id)
        .values(status=ProjectStatus.cancelled, status_message="Upload cancelled by user")
    )
    await session.commit()
    Path(upload.staging_path).unlink(missing_ok=True)
    return await _owned_upload(upload_id, session, user)
