import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.api.schemas import JobOut
from msclips.core.db import get_session
from msclips.core.users import current_user
from msclips.models import Job, JobStatus, Project, ProjectStatus, User

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _owned_job(job_id: uuid.UUID, session: AsyncSession, user: User) -> Job:
    job = await session.get(Job, job_id, populate_existing=True)
    if job is None:
        raise HTTPException(404, "Job not found")
    project = await session.get(Project, job.project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    return await _owned_job(job_id, session, user)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)
):
    job = await _owned_job(job_id, session, user)
    if job.status != JobStatus.queued:
        raise HTTPException(
            409,
            "Only queued jobs can be cancelled safely."
            if job.status == JobStatus.running
            else f"Job is already {job.status.value}.",
        )
    # The worker re-reads the row before starting and skips cancelled jobs.
    res = await session.execute(
        update(Job).where(Job.id == job.id, Job.status == JobStatus.queued).values(status=JobStatus.cancelled)
    )
    if res.rowcount != 1:
        raise HTTPException(409, "Job started before it could be cancelled.")
    await session.execute(
        update(Project)
        .where(Project.id == job.project_id)
        .values(status=ProjectStatus.failed, status_message="Processing cancelled by user. Use 'Retry processing' to run it again.")
    )
    await session.commit()
    return await _owned_job(job_id, session, user)
