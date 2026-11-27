"""Helpers that build project response objects with explicit loads (no lazy IO)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.api.schemas import (
    AssetOut,
    JobOut,
    ProjectDetail,
    ProjectSummary,
    UploadOut,
    VideoMetadataOut,
)
from msclips.models import AssetKind, Job, MediaAsset, Project, UploadSession, VideoMetadata


async def summaries(session: AsyncSession, projects: list[Project]) -> list[ProjectSummary]:
    if not projects:
        return []
    ids = [p.id for p in projects]
    assets = (
        await session.execute(select(MediaAsset).where(MediaAsset.project_id.in_(ids)))
    ).scalars().all()
    src_ids = [a.id for a in assets if a.kind == AssetKind.source]
    metas = {
        m.asset_id: m
        for m in (
            await session.execute(select(VideoMetadata).where(VideoMetadata.asset_id.in_(src_ids)))
        ).scalars().all()
    } if src_ids else {}
    uploads: dict[uuid.UUID, UploadSession] = {}
    for u in (
        await session.execute(
            select(UploadSession).where(UploadSession.project_id.in_(ids)).order_by(UploadSession.created_at)
        )
    ).scalars().all():
        uploads[u.project_id] = u
    by_project: dict[uuid.UUID, list[MediaAsset]] = {}
    for a in assets:
        by_project.setdefault(a.project_id, []).append(a)

    out = []
    for p in projects:
        pa = by_project.get(p.id, [])
        src = next((a for a in pa if a.id == p.source_asset_id), None)
        meta = metas.get(src.id) if src else None
        up = uploads.get(p.id)
        out.append(
            ProjectSummary(
                id=p.id,
                name=p.name,
                status=p.status,
                status_message=p.status_message,
                created_at=p.created_at,
                updated_at=p.updated_at,
                has_thumbnail=any(a.kind == AssetKind.thumbnail for a in pa),
                source_filename=src.filename if src else (up.filename if up else None),
                source_size_bytes=src.size_bytes if src else (up.size_bytes if up else None),
                duration_s=meta.duration_s if meta else None,
                width=meta.display_width if meta else None,
                height=meta.display_height if meta else None,
                aspect_ratio=meta.aspect_ratio if meta else None,
            )
        )
    return out


async def detail(session: AsyncSession, project: Project) -> ProjectDetail:
    await session.refresh(project)
    (summary,) = await summaries(session, [project])
    src = await session.get(MediaAsset, project.source_asset_id) if project.source_asset_id else None
    meta = await session.get(VideoMetadata, src.id) if src else None
    upload = (
        await session.execute(
            select(UploadSession)
            .where(UploadSession.project_id == project.id)
            .order_by(UploadSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    jobs = (
        await session.execute(select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc()))
    ).scalars().all()
    return ProjectDetail(
        **summary.model_dump(),
        source=AssetOut.model_validate(src) if src else None,
        metadata=VideoMetadataOut.model_validate(meta) if meta else None,
        upload=UploadOut.model_validate(upload) if upload else None,
        jobs=[JobOut.model_validate(j) for j in jobs],
    )
