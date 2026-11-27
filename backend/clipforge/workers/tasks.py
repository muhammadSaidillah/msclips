"""Worker tasks. Each task owns the state transitions of its `jobs` row.

Progress values are written only at real step boundaries, so the UI never shows invented progress.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from arq import Retry
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.core.config import get_settings
from clipforge.core.db import sessionmaker
from clipforge.media.probe import MediaError, make_thumbnail, probe, verify_decodable
from clipforge.models import (
    AssetKind,
    Job,
    JobStatus,
    MediaAsset,
    Project,
    ProjectStatus,
    UploadSession,
    VideoMetadata,
)
from clipforge.storage import Storage, get_storage

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


async def _set_job(session: AsyncSession, job_id: uuid.UUID, **values) -> None:
    await session.execute(update(Job).where(Job.id == job_id).values(**values))
    await session.commit()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_key(project_id: uuid.UUID, filename: str) -> str:
    ext = Path(filename).suffix.lower() or ".bin"
    return f"projects/{project_id}/source{ext}"


async def _ingest_upload(session: AsyncSession, storage: Storage, project: Project, job_id: uuid.UUID) -> MediaAsset:
    """Move the assembled upload from staging into object storage and register it as the source asset."""
    upload = (
        await session.execute(
            select(UploadSession)
            .where(UploadSession.project_id == project.id)
            .order_by(UploadSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if upload is None:
        raise MediaError("No upload found for this project.")
    staging = Path(upload.staging_path)
    if not staging.is_file():
        raise MediaError("The uploaded file is no longer in staging. Please upload it again.")
    actual = staging.stat().st_size
    if actual != upload.size_bytes:
        raise MediaError(f"Uploaded size {actual} bytes does not match declared {upload.size_bytes} bytes.")

    await _set_job(session, job_id, stage="verifying upload integrity", progress=0.05)
    digest = await asyncio.to_thread(_sha256, staging)

    await _set_job(session, job_id, stage="storing source video", progress=0.25)
    key = source_key(project.id, upload.filename)
    size = await storage.put_file(staging, key, upload.content_type)
    asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.source,
        storage_backend=storage.backend,
        storage_key=key,
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=size,
        sha256=digest,
    )
    session.add(asset)
    await session.flush()
    project.source_asset_id = asset.id
    await session.commit()
    return asset


async def probe_source(ctx: dict, job_id_str: str) -> str:
    job_id = uuid.UUID(job_id_str)
    storage = get_storage()
    settings = get_settings()
    async with sessionmaker()() as session:
        job = await session.get(Job, job_id)
        if job is None:
            log.warning("job %s vanished", job_id)
            return "missing"
        if job.status in (JobStatus.cancelled, JobStatus.succeeded):
            return job.status.value
        project = await session.get(Project, job.project_id)
        if project is None:
            return "missing-project"
        project_id = project.id

        attempt = job.attempts + 1
        await _set_job(
            session, job_id, status=JobStatus.running, attempts=attempt, started_at=_now(),
            error=None, stage="starting", progress=0.0,
        )
        project.status = ProjectStatus.processing
        project.status_message = "Extracting video metadata"
        await session.commit()

        tmpdir = Path(tempfile.mkdtemp(prefix="cf-probe-", dir=settings.data_dir if settings.data_dir.exists() else None))
        try:
            asset = await session.get(MediaAsset, project.source_asset_id) if project.source_asset_id else None
            if asset is None:
                asset = await _ingest_upload(session, storage, project, job_id)

            await _set_job(session, job_id, stage="reading video metadata", progress=0.5)
            local = storage.local_path(asset.storage_key)
            if local is None:
                local = tmpdir / Path(asset.storage_key).name
                await storage.get_to_file(asset.storage_key, local)
            info = await probe(local)
            if info.duration_s > settings.max_duration_s:
                raise MediaError(
                    f"Video is {info.duration_s / 3600:.1f} h long; the limit is {settings.max_duration_s / 3600:.1f} h."
                )

            await _set_job(session, job_id, stage="verifying frames decode", progress=0.65)
            await verify_decodable(local, min(1.0, info.duration_s / 2))

            await _set_job(session, job_id, stage="creating thumbnail", progress=0.8)
            thumb_local = tmpdir / "thumb.jpg"
            await make_thumbnail(local, thumb_local, at_s=info.duration_s * 0.1)
            thumb_key = f"projects/{project.id}/thumbnail.jpg"
            thumb_size = await storage.put_file(thumb_local, thumb_key, "image/jpeg")

            # Persist metadata + thumbnail atomically
            existing_meta = await session.get(VideoMetadata, asset.id)
            if existing_meta is not None:
                await session.delete(existing_meta)
                await session.flush()
            session.add(VideoMetadata(asset_id=asset.id, **info.as_columns()))
            old_thumbs = (
                await session.execute(
                    select(MediaAsset).where(MediaAsset.project_id == project.id, MediaAsset.kind == AssetKind.thumbnail)
                )
            ).scalars().all()
            for t in old_thumbs:
                await session.delete(t)
            session.add(
                MediaAsset(
                    project_id=project.id, kind=AssetKind.thumbnail, storage_backend=storage.backend,
                    storage_key=thumb_key, filename="thumbnail.jpg", content_type="image/jpeg", size_bytes=thumb_size,
                )
            )
            project.status = ProjectStatus.ready
            project.status_message = None
            await session.commit()
            await _set_job(
                session, job_id, status=JobStatus.succeeded, stage="done", progress=1.0, finished_at=_now(),
                result={"duration_s": info.duration_s, "width": info.display_width, "height": info.display_height},
            )
            return "succeeded"
        except MediaError as e:
            await session.rollback()
            await _fail(session, job_id, project_id, str(e))
            return "failed"
        except Exception as e:  # environmental / transient: retry with backoff
            await session.rollback()
            log.exception("probe_source attempt %s failed", attempt)
            job = await session.get(Job, job_id, populate_existing=True)
            if job and attempt < job.max_attempts:
                await _set_job(session, job_id, status=JobStatus.queued, stage="waiting to retry", error=str(e)[:1000])
                raise Retry(defer=min(60, 5 * 2 ** (attempt - 1))) from e
            await _fail(session, job_id, project_id, f"Processing failed after {attempt} attempts: {e}")
            return "failed"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


async def _fail(session: AsyncSession, job_id: uuid.UUID, project_id: uuid.UUID, message: str) -> None:
    await _set_job(session, job_id, status=JobStatus.failed, error=message[:2000], finished_at=_now())
    await session.execute(
        update(Project).where(Project.id == project_id).values(status=ProjectStatus.failed, status_message=message[:2000])
    )
    await session.commit()
