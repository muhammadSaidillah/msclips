import shutil

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.api.projects_query import summaries
from msclips.api.schemas import DashboardOut
from msclips.core.config import get_settings
from msclips.core.db import get_session
from msclips.core.users import current_user
from msclips.models import AssetKind, Job, JobStatus, MediaAsset, Project, ProjectStatus, User, VideoMetadata
from msclips.storage import get_storage
from msclips.workers.queue import Queue, get_queue

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session), queue: Queue = Depends(get_queue)):
    checks: dict[str, dict] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as e:
        checks["database"] = {"ok": False, "error": str(e)[:300]}
    try:
        checks["queue"] = {"ok": await queue.ping()}
    except Exception as e:
        checks["queue"] = {"ok": False, "error": str(e)[:300]}
    try:
        await get_storage().check()
        checks["storage"] = {"ok": True, "backend": get_settings().storage_backend}
    except Exception as e:
        checks["storage"] = {"ok": False, "error": str(e)[:300]}
    s = get_settings()
    checks["ffmpeg"] = {"ok": bool(shutil.which(s.ffmpeg_bin)) and bool(shutil.which(s.ffprobe_bin))}
    ok = all(c["ok"] for c in checks.values())
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    counts = dict(
        (await session.execute(
            select(Project.status, func.count()).where(Project.owner_id == user.id).group_by(Project.status)
        )).all()
    )
    project_counts = {s.value: int(counts.get(s, 0)) for s in ProjectStatus}
    src = (
        select(func.coalesce(func.sum(MediaAsset.size_bytes), 0), func.coalesce(func.sum(VideoMetadata.duration_s), 0.0))
        .select_from(MediaAsset)
        .join(Project, Project.source_asset_id == MediaAsset.id)
        .outerjoin(VideoMetadata, VideoMetadata.asset_id == MediaAsset.id)
        .where(Project.owner_id == user.id, MediaAsset.kind == AssetKind.source)
    )
    total_bytes, total_duration = (await session.execute(src)).one()
    active = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .join(Project, Project.id == Job.project_id)
            .where(Project.owner_id == user.id, Job.status.in_([JobStatus.queued, JobStatus.running]))
        )
    ).scalar_one()
    recent = (
        await session.execute(
            select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc()).limit(6)
        )
    ).scalars().all()
    return DashboardOut(
        project_counts=project_counts,
        total_projects=sum(project_counts.values()),
        total_source_bytes=int(total_bytes),
        total_source_duration_s=float(total_duration),
        active_jobs=int(active),
        recent_projects=await summaries(session, list(recent)),
    )
