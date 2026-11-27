"""Analysis (transcribe + AI clip discovery), candidate review, rendering and downloads."""

import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from msclips.api.deps import owned_project
from msclips.api.routers.projects import _serve
from msclips.api.schemas import (
    AnalysisCreate,
    AnalysisRunOut,
    AnalysisState,
    CandidateOut,
    CandidateUpdate,
    JobOut,
    RenderCreate,
    RenderOut,
    TranscriptInfo,
)
from msclips.core.config import get_settings
from msclips.core.db import get_session
from msclips.core.users import current_user
from msclips.media import styles
from msclips.models import (
    AnalysisRun,
    AnalysisStatus,
    CandidateStatus,
    ClipCandidate,
    ClipRender,
    Job,
    JobStatus,
    JobType,
    MediaAsset,
    Project,
    ProjectStatus,
    RenderStatus,
    Transcript,
    User,
)
from msclips.storage import get_storage
from msclips.workers.queue import Queue, get_queue

router = APIRouter(tags=["clips"])


@router.get("/styles")
async def list_styles():
    """Editing styles that the renderer can apply, plus how the automatic pick works."""
    return {
        "default": "auto",
        "styles": styles.catalog(),
        "auto": {"by_editing_style": styles.AUTO_BY_EDITING_STYLE, "by_category": styles.AUTO_BY_CATEGORY,
                 "fallback": styles.AUTO_DEFAULT},
    }


@router.get("/capabilities")
async def capabilities():
    s = get_settings()
    return {
        "transcription": {"engine": f"faster-whisper:{s.whisper_model}", "device": s.whisper_device},
        "ai": {"model": s.anthropic_model, "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))},
    }


async def _enqueue(session: AsyncSession, queue: Queue, job: Job, task: str) -> None:
    try:
        job.arq_job_id = await queue.enqueue_job_task(task, job.id)
        await session.commit()
    except Exception as e:
        job.status = JobStatus.failed
        job.error = f"Job queue unavailable: {e}"
        await session.commit()
        raise HTTPException(503, job.error) from e


@router.post("/projects/{project_id}/analysis", response_model=AnalysisState, status_code=202)
async def start_analysis(
    body: AnalysisCreate,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_session),
    queue: Queue = Depends(get_queue),
):
    if project.status != ProjectStatus.ready:
        raise HTTPException(409, "The video must finish processing before it can be analysed.")
    if body.min_duration_s >= body.max_duration_s:
        raise HTTPException(422, "Minimum duration must be shorter than maximum duration.")
    active = (await session.execute(
        select(func.count()).select_from(Job).where(
            Job.project_id == project.id, Job.type == JobType.analyze,
            Job.status.in_([JobStatus.queued, JobStatus.running]))
    )).scalar_one()
    if active:
        raise HTTPException(409, "An analysis is already running for this project.")
    run = AnalysisRun(
        project_id=project.id, clip_count=body.clip_count, min_duration_s=body.min_duration_s,
        max_duration_s=body.max_duration_s, language=body.language, status=AnalysisStatus.queued,
    )
    session.add(run)
    await session.flush()
    job = Job(project_id=project.id, type=JobType.analyze, payload={"analysis_run_id": str(run.id)}, max_attempts=3)
    session.add(job)
    await session.flush()
    run.job_id = job.id
    await session.commit()
    await _enqueue(session, queue, job, "analyze")
    return await _state(session, project)


async def _state(session: AsyncSession, project: Project) -> AnalysisState:
    run = (await session.execute(
        select(AnalysisRun).where(AnalysisRun.project_id == project.id)
        .order_by(AnalysisRun.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return AnalysisState(run=None, job=None, transcript=None, candidates=[])
    await session.refresh(run)
    job = await session.get(Job, run.job_id, populate_existing=True) if run.job_id else None
    tr = await session.get(Transcript, run.transcript_id) if run.transcript_id else None
    cands = (await session.execute(
        select(ClipCandidate).where(ClipCandidate.analysis_run_id == run.id).order_by(ClipCandidate.rank)
    )).scalars().all()
    return AnalysisState(
        run=AnalysisRunOut.model_validate(run),
        job=JobOut.model_validate(job) if job else None,
        transcript=TranscriptInfo(
            id=tr.id, language=tr.language, language_probability=tr.language_probability, engine=tr.engine,
            duration_s=tr.duration_s, segment_count=len(tr.segments),
            word_count=sum(len(sg["words"]) for sg in tr.segments),
        ) if tr else None,
        candidates=[CandidateOut.model_validate(c) for c in cands],
    )


@router.get("/projects/{project_id}/analysis", response_model=AnalysisState)
async def get_analysis(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    return await _state(session, project)


@router.get("/projects/{project_id}/transcript")
async def get_transcript(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    tr = (await session.execute(
        select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if tr is None:
        raise HTTPException(404, "No transcript yet")
    return {"language": tr.language, "engine": tr.engine, "segments": tr.segments}


async def _owned_candidate(cid: uuid.UUID, session: AsyncSession, user: User) -> ClipCandidate:
    c = await session.get(ClipCandidate, cid)
    if c is None:
        raise HTTPException(404, "Candidate not found")
    p = await session.get(Project, c.project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Candidate not found")
    return c


@router.patch("/candidates/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: uuid.UUID, body: CandidateUpdate,
    session: AsyncSession = Depends(get_session), user: User = Depends(current_user),
):
    c = await _owned_candidate(candidate_id, session, user)
    c.status = CandidateStatus(body.status)
    await session.commit()
    await session.refresh(c)
    return c


@router.post("/projects/{project_id}/renders", response_model=list[RenderOut], status_code=202)
async def start_renders(
    body: RenderCreate,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_session),
    queue: Queue = Depends(get_queue),
):
    cands = (await session.execute(
        select(ClipCandidate).where(ClipCandidate.id.in_(body.candidate_ids), ClipCandidate.project_id == project.id)
    )).scalars().all()
    if len(cands) != len(set(body.candidate_ids)):
        raise HTTPException(404, "One or more clips were not found in this project.")
    created = []
    for c in sorted(cands, key=lambda x: x.rank):
        render = ClipRender(
            project_id=project.id, candidate_id=c.id, status=RenderStatus.queued,
            settings={"edit_style": body.edit_style, "captions": body.captions, "show_hook": body.show_hook,
                      "width": 1080, "height": 1920, "fps": 30},
        )
        session.add(render)
        await session.flush()
        job = Job(project_id=project.id, type=JobType.render_clip, payload={"render_id": str(render.id)})
        session.add(job)
        await session.flush()
        render.job_id = job.id
        c.status = CandidateStatus.selected
        created.append((render, job))
    await session.commit()
    for _, job in created:
        await _enqueue(session, queue, job, "render_clip")
    return await _renders(session, project, only={r.id for r, _ in created})


async def _renders(session: AsyncSession, project: Project, only: set | None = None) -> list[RenderOut]:
    rows = (await session.execute(
        select(ClipRender, ClipCandidate).join(ClipCandidate, ClipCandidate.id == ClipRender.candidate_id)
        .where(ClipRender.project_id == project.id).order_by(ClipRender.created_at.desc())
    )).all()
    out = []
    for r, c in rows:
        if only is not None and r.id not in only:
            continue
        await session.refresh(r)
        job = await session.get(Job, r.job_id, populate_existing=True) if r.job_id else None
        asset = await session.get(MediaAsset, r.asset_id) if r.asset_id else None
        out.append(RenderOut(
            id=r.id, candidate_id=c.id, rank=c.rank, title=c.title, duration_s=round(c.end_s - c.start_s, 2),
            status=r.status.value, error=r.error, settings=r.settings, crop=r.crop, qc=r.qc,
            job=JobOut.model_validate(job) if job else None,
            file_size_bytes=asset.size_bytes if asset else None, filename=asset.filename if asset else None,
            created_at=r.created_at,
        ))
    return out


@router.get("/projects/{project_id}/renders", response_model=list[RenderOut])
async def list_renders(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    return await _renders(session, project)


async def _owned_render(rid: uuid.UUID, session: AsyncSession, user: User) -> ClipRender:
    r = await session.get(ClipRender, rid)
    if r is None:
        raise HTTPException(404, "Render not found")
    p = await session.get(Project, r.project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Render not found")
    return r


@router.get("/renders/{render_id}/file")
async def render_file(
    render_id: uuid.UUID, download: bool = False,
    session: AsyncSession = Depends(get_session), user: User = Depends(current_user),
):
    r = await _owned_render(render_id, session, user)
    if r.status != RenderStatus.succeeded or r.asset_id is None:
        raise HTTPException(409, "This clip has not rendered successfully.")
    asset = await session.get(MediaAsset, r.asset_id)
    return await _serve(asset, inline=not download)


@router.get("/projects/{project_id}/renders.zip")
async def renders_zip(project: Project = Depends(owned_project), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(ClipRender, MediaAsset).join(MediaAsset, MediaAsset.id == ClipRender.asset_id)
        .where(ClipRender.project_id == project.id, ClipRender.status == RenderStatus.succeeded)
    )).all()
    if not rows:
        raise HTTPException(404, "No rendered clips to download yet.")
    storage = get_storage()
    fd, zpath = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as zf:
        names: set[str] = set()
        for _, asset in rows:
            local = storage.local_path(asset.storage_key)
            if local is None:
                local = Path(td) / f"{asset.id}.mp4"
                await storage.get_to_file(asset.storage_key, local)
            name = asset.filename
            while name in names:
                name = "_" + name
            names.add(name)
            zf.write(local, name)
    safe = "".join(ch for ch in project.name if ch.isalnum() or ch in " -_")[:60].strip() or "clips"
    return FileResponse(zpath, media_type="application/zip", filename=f"{safe} - clips.zip",
                        background=BackgroundTask(os.unlink, zpath))
