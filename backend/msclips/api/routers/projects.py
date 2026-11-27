import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.api.deps import owned_project
from msclips.api.projects_query import detail, summaries
from msclips.api.schemas import JobOut, ProjectDetail, ProjectList, ProjectUpdate
from msclips.core.db import get_session
from msclips.core.users import current_user
from msclips.models import (
    AssetKind,
    Job,
    JobStatus,
    JobType,
    MediaAsset,
    Project,
    ProjectStatus,
    UploadSession,
    UploadStatus,
    User,
)
from msclips.storage import get_storage
from msclips.workers.queue import Queue, get_queue

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectList)
async def list_projects(
    q: str | None = Query(default=None, max_length=200),
    status: ProjectStatus | None = None,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    stmt = select(Project).where(Project.owner_id == user.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(like),
                Project.id.in_(select(UploadSession.project_id).where(UploadSession.filename.ilike(like))),
            )
        )
    if status:
        stmt = stmt.where(Project.status == status)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Project.created_at.desc()).limit(limit).offset(offset))
    ).scalars().all()
    return ProjectList(items=await summaries(session, list(rows)), total=total, limit=limit, offset=offset)


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    return await detail(session, project)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def rename_project(
    body: ProjectUpdate, project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)
):
    project.name = body.name.strip()
    if not project.name:
        raise HTTPException(422, "Name cannot be empty")
    await session.commit()
    return await detail(session, project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    running = (
        await session.execute(
            select(func.count()).where(Job.project_id == project.id, Job.status == JobStatus.running)
        )
    ).scalar_one()
    if running:
        raise HTTPException(409, "A processing job is running for this project. Wait for it to finish, then delete.")
    storage = get_storage()
    assets = (await session.execute(select(MediaAsset).where(MediaAsset.project_id == project.id))).scalars().all()
    uploads = (
        await session.execute(select(UploadSession).where(UploadSession.project_id == project.id))
    ).scalars().all()
    for a in assets:
        await storage.delete(a.storage_key)
    for u in uploads:
        Path(u.staging_path).unlink(missing_ok=True)
    project.source_asset_id = None
    await session.flush()
    await session.delete(project)
    await session.commit()


@router.post("/{project_id}/reprocess", response_model=JobOut, status_code=202)
async def reprocess(
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_session),
    queue: Queue = Depends(get_queue),
):
    active = (
        await session.execute(
            select(func.count()).where(
                Job.project_id == project.id, Job.status.in_([JobStatus.queued, JobStatus.running])
            )
        )
    ).scalar_one()
    if active:
        raise HTTPException(409, "Processing is already queued or running.")
    if project.source_asset_id is None:
        upload = (
            await session.execute(
                select(UploadSession)
                .where(UploadSession.project_id == project.id, UploadSession.status == UploadStatus.completed)
                .order_by(UploadSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if upload is None or not Path(upload.staging_path).is_file():
            raise HTTPException(409, "There is no stored or staged video to process. Upload the video again.")
    job = Job(project_id=project.id, type=JobType.probe_source)
    session.add(job)
    project.status = ProjectStatus.processing
    project.status_message = "Queued for metadata extraction"
    await session.commit()
    try:
        job.arq_job_id = await queue.enqueue_job_task("probe_source", job.id)
    except Exception as e:
        job.status = JobStatus.failed
        job.error = f"Job queue unavailable: {e}"
        project.status = ProjectStatus.failed
        project.status_message = job.error
        await session.commit()
        raise HTTPException(503, job.error) from e
    await session.commit()
    await session.refresh(job)
    return job


async def _asset(session: AsyncSession, project: Project, kind: AssetKind) -> MediaAsset:
    if kind == AssetKind.source:
        asset = await session.get(MediaAsset, project.source_asset_id) if project.source_asset_id else None
    else:
        asset = (
            await session.execute(
                select(MediaAsset)
                .where(MediaAsset.project_id == project.id, MediaAsset.kind == kind)
                .order_by(MediaAsset.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(404, f"No {kind.value} available for this project")
    return asset


async def _serve(asset: MediaAsset, *, inline: bool = True):
    storage = get_storage()
    local = storage.local_path(asset.storage_key)
    if local is not None:
        if not local.is_file():
            raise HTTPException(410, "Stored file is missing")
        return FileResponse(
            local,
            media_type=asset.content_type or "application/octet-stream",
            filename=asset.filename,
            content_disposition_type="inline" if inline else "attachment",
        )
    url = await storage.presigned_url(asset.storage_key)
    if not url:
        raise HTTPException(500, "Storage backend cannot serve this file")
    return RedirectResponse(url, status_code=307)


@router.get("/{project_id}/source")
async def get_source(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    return await _serve(await _asset(session, project, AssetKind.source))


@router.get("/{project_id}/thumbnail")
async def get_thumbnail(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    return await _serve(await _asset(session, project, AssetKind.thumbnail))
