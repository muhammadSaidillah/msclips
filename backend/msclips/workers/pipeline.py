"""Analysis (transcription + AI clip discovery) and clip rendering tasks."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path

from arq import Retry
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.ai import discovery
from msclips.ai.transcribe import transcribe
from msclips.core.config import get_settings
from msclips.core.db import sessionmaker
from msclips.media.audio import decode_pcm_16k
from msclips.media.probe import MediaError
from msclips.media.qc import run_qc
from msclips.media.reframe import plan_crop
from msclips.media.render import LAND_W, OUT_W, static_plan, zoom_schedule
from msclips.media.render import render_clip as ffmpeg_render
from msclips.media.showcase import make_assets
from msclips.media.styles import resolve_style
from msclips.media.subtitles import SIDE_MARGIN, clip_words, write_ass
from msclips.models import (
    AnalysisRun,
    AnalysisStatus,
    AssetKind,
    ClipCandidate,
    ClipRender,
    Job,
    JobStatus,
    MediaAsset,
    Project,
    RenderStatus,
    Transcript,
    VideoMetadata,
)
from msclips.storage import Storage, get_storage
from msclips.workers.tasks import _now, _set_job

log = logging.getLogger(__name__)


class _Progress:
    """Thread-safe progress holder flushed to the DB by an async loop."""

    def __init__(self) -> None:
        self.value = 0.0

    def set(self, v: float) -> None:
        self.value = v


async def _flush_progress(job_id: uuid.UUID, holder: _Progress, lo: float, hi: float, stage: str, stop: asyncio.Event):
    last = -1.0
    async with sessionmaker()() as s:
        while not stop.is_set():
            v = lo + (hi - lo) * holder.value
            if abs(v - last) >= 0.005:
                await _set_job(s, job_id, progress=round(v, 4), stage=stage)
                last = v
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except TimeoutError:
                pass


async def _source_local(storage: Storage, asset: MediaAsset, tmpdir: Path) -> Path:
    local = storage.local_path(asset.storage_key)
    if local is None:
        local = tmpdir / Path(asset.storage_key).name
        await storage.get_to_file(asset.storage_key, local)
    return local


async def _begin(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    job = await session.get(Job, job_id)
    if job is None or job.status in (JobStatus.cancelled, JobStatus.succeeded):
        return None
    await _set_job(session, job_id, status=JobStatus.running, attempts=job.attempts + 1, started_at=_now(),
                   error=None, stage="starting", progress=0.0)
    await session.refresh(job)
    return job


async def _retry_or_fail(session: AsyncSession, job_id: uuid.UUID, e: Exception, on_fail) -> None:
    job = await session.get(Job, job_id, populate_existing=True)
    if job and job.attempts < job.max_attempts:
        await _set_job(session, job_id, status=JobStatus.queued, stage="waiting to retry", error=str(e)[:1000])
        raise Retry(defer=min(60, 5 * 2 ** (job.attempts - 1))) from e
    msg = f"Failed after {job.attempts if job else '?'} attempts: {e}"
    await _set_job(session, job_id, status=JobStatus.failed, error=msg[:2000], finished_at=_now())
    await on_fail(msg)


# --------------------------------------------------------------------------------------------- analyze


async def analyze(ctx: dict, job_id_str: str) -> str:
    job_id = uuid.UUID(job_id_str)
    storage = get_storage()
    s = get_settings()
    async with sessionmaker()() as session:
        job = await _begin(session, job_id)
        if job is None:
            return "skipped"
        run = await session.get(AnalysisRun, uuid.UUID(job.payload["analysis_run_id"]))
        project = await session.get(Project, job.project_id)
        run_id = run.id

        async def mark_failed(msg: str):
            await session.execute(update(AnalysisRun).where(AnalysisRun.id == run_id).values(
                status=AnalysisStatus.failed, error=msg[:2000]))
            await session.commit()

        tmpdir = Path(tempfile.mkdtemp(prefix="ms-analyze-"))
        try:
            asset = await session.get(MediaAsset, project.source_asset_id) if project.source_asset_id else None
            meta = await session.get(VideoMetadata, asset.id) if asset else None
            if asset is None or meta is None:
                raise MediaError("The source video is not ready yet.")
            if not meta.has_audio:
                raise MediaError("This video has no audio track, so there is no speech to analyse.")

            transcript = (await session.execute(
                select(Transcript).where(Transcript.project_id == project.id,
                                         Transcript.requested_language.is_(None) if run.language is None
                                         else Transcript.requested_language == run.language)
                .order_by(Transcript.created_at.desc()).limit(1)
            )).scalar_one_or_none()

            if transcript is None:
                run.status = AnalysisStatus.transcribing
                await session.commit()
                await _set_job(session, job_id, stage="extracting audio", progress=0.02)
                local = await _source_local(storage, asset, tmpdir)
                audio = await decode_pcm_16k(local)
                holder, stop = _Progress(), asyncio.Event()
                flusher = asyncio.create_task(
                    _flush_progress(job_id, holder, 0.05, 0.75, "transcribing speech", stop))
                try:
                    result = await asyncio.to_thread(transcribe, audio, run.language, holder.set)
                finally:
                    stop.set()
                    await flusher
                if not result.segments:
                    raise MediaError("No speech was detected in this video.")
                transcript = Transcript(
                    project_id=project.id, requested_language=run.language, language=result.language,
                    language_probability=result.language_probability, engine=result.engine,
                    duration_s=result.duration_s, text=result.text, segments=result.segments,
                )
                session.add(transcript)
                await session.flush()
            run.transcript_id = transcript.id
            run.status = AnalysisStatus.analyzing
            await session.commit()

            await _set_job(session, job_id, stage="AI is reading the transcript and choosing clips", progress=0.78)
            candidates, notes, usage, model = await asyncio.to_thread(
                discovery.discover, transcript.segments, transcript.language, run.clip_count,
                run.min_duration_s, run.max_duration_s, meta.duration_s,
            )
            for c in candidates:
                session.add(ClipCandidate(
                    project_id=project.id, analysis_run_id=run.id, rank=c.rank, title=c.title, start_s=c.start_s,
                    end_s=c.end_s, hook=c.hook, category=c.category, reason=c.reason,
                    transcript_text=c.transcript_text, scores=c.scores, score=c.score, confidence=c.confidence,
                    editing_style=c.editing_style,
                ))
            if len(candidates) < run.clip_count:
                extra = f"Found {len(candidates)} of {run.clip_count} requested clips that met the rules."
                notes = f"{notes} {extra}".strip() if notes else extra
            run.status = AnalysisStatus.succeeded
            run.notes = notes or None
            run.usage = usage
            run.model = model
            await session.commit()
            await _set_job(session, job_id, status=JobStatus.succeeded, stage="done", progress=1.0,
                           finished_at=_now(), result={"candidates": len(candidates)})
            return "succeeded"
        except (MediaError, discovery.DiscoveryError) as e:
            await session.rollback()
            await _set_job(session, job_id, status=JobStatus.failed, error=str(e)[:2000], finished_at=_now())
            await mark_failed(str(e))
            return "failed"
        except Exception as e:
            await session.rollback()
            log.exception("analyze failed")
            await _retry_or_fail(session, job_id, e, mark_failed)
            return "failed"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- render


async def render_clip(ctx: dict, job_id_str: str) -> str:
    job_id = uuid.UUID(job_id_str)
    storage = get_storage()
    async with sessionmaker()() as session:
        job = await _begin(session, job_id)
        if job is None:
            return "skipped"
        render = await session.get(ClipRender, uuid.UUID(job.payload["render_id"]))
        render_id = render.id

        async def mark_failed(msg: str):
            await session.execute(update(ClipRender).where(ClipRender.id == render_id).values(
                status=RenderStatus.failed, error=msg[:2000]))
            await session.commit()

        tmpdir = Path(tempfile.mkdtemp(prefix="ms-render-"))
        qc_report: dict | None = None
        crop_json: dict | None = None
        try:
            cand = await session.get(ClipCandidate, render.candidate_id)
            project = await session.get(Project, render.project_id)
            asset = await session.get(MediaAsset, project.source_asset_id)
            meta = await session.get(VideoMetadata, asset.id)
            run = await session.get(AnalysisRun, cand.analysis_run_id)
            transcript = await session.get(Transcript, run.transcript_id)
            render.status = RenderStatus.rendering
            render.error = None
            await session.commit()

            local = await _source_local(storage, asset, tmpdir)
            duration = cand.end_s - cand.start_s
            await _set_job(session, job_id, stage="finding the speaker for 9:16 framing", progress=0.05)
            plan = await plan_crop(local, cand.start_s, duration, meta.display_width, meta.display_height)

            settings = dict(render.settings or {})
            requested = settings.get("edit_style") or settings.get("subtitle_style", "bold")
            captions = settings.get("captions", True)
            if requested == "none":  # legacy "no captions" choice
                requested, captions = "clean", False
            landscape = meta.display_width > meta.display_height
            style, reason = resolve_style(requested, cand.editing_style, cand.category, landscape)
            settings.update(resolved_style=style.id, resolved_style_name=style.name, style_reason=reason)
            render.settings = settings
            await session.commit()
            if style.framing == "static":
                plan = static_plan(plan, duration)
            sc = style.showcase

            words = clip_words(transcript.segments, cand.start_s, cand.end_s)
            ass_path = None
            lines: list[tuple[str, int]] = []
            play = (LAND_W, 1080) if sc and sc.landscape else (OUT_W, 1920)
            if captions:
                ass_path = tmpdir / "captions.ass"
                boost = set((cand.title + " " + (cand.hook or "")).split())
                lines = write_ass(ass_path, words, style=style, play=play, boost=boost,
                                  hook=cand.hook if settings.get("show_hook", True) else None)
            zoom = zoom_schedule(style.zoom, words, duration)
            assets = make_assets(sc, tmpdir) if sc else None

            holder, stop = _Progress(), asyncio.Event()
            flusher = asyncio.create_task(_flush_progress(job_id, holder, 0.2, 0.88, "rendering 1080x1920 video", stop))
            out = tmpdir / "clip.mp4"
            try:
                await ffmpeg_render(local, out, cand.start_s, cand.end_s, plan, ass_path, holder.set,
                                    style=style, zoom=zoom, showcase_assets=assets)
            finally:
                stop.set()
                await flusher

            await _set_job(session, job_id, stage="checking the rendered file", progress=0.9)
            side = SIDE_MARGIN * play[0] / OUT_W
            limit = (play[0] - 2 * side) * (2 if style.caption.layout == "line" else 1)
            qc_plan = plan if not (sc and sc.landscape) else replace(plan, mode="fit")
            qc = await run_qc(out, duration, lines, limit, qc_plan, captions_enabled=captions)
            qc_report, crop_json = qc, plan.to_json()
            render.crop = crop_json
            render.qc = qc
            if qc["status"] == "fail":
                failed = "; ".join(c["detail"] for c in qc["checks"] if c["status"] == "fail")
                raise MediaError(f"Quality check failed: {failed}")

            key = f"projects/{project.id}/clips/{render.id}.mp4"
            size = await storage.put_file(out, key, "video/mp4")
            safe_title = "".join(ch for ch in cand.title if ch.isalnum() or ch in " -_")[:60].strip() or "clip"
            clip_asset = MediaAsset(
                project_id=project.id, kind=AssetKind.clip, storage_backend=storage.backend, storage_key=key,
                filename=f"{cand.rank:02d} - {safe_title}.mp4", content_type="video/mp4", size_bytes=size,
            )
            session.add(clip_asset)
            await session.flush()
            render.asset_id = clip_asset.id
            render.status = RenderStatus.succeeded
            await session.commit()
            await _set_job(session, job_id, status=JobStatus.succeeded, stage="done", progress=1.0,
                           finished_at=_now(), result={"qc": qc["status"]})
            return "succeeded"
        except MediaError as e:
            await session.rollback()
            await session.execute(update(ClipRender).where(ClipRender.id == render_id).values(
                qc=qc_report, crop=crop_json))
            await _set_job(session, job_id, status=JobStatus.failed, error=str(e)[:2000], finished_at=_now())
            await mark_failed(str(e))
            return "failed"
        except Exception as e:
            await session.rollback()
            log.exception("render failed")
            await _retry_or_fail(session, job_id, e, mark_failed)
            return "failed"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
