import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectStatus(str, enum.Enum):
    uploading = "uploading"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"


class UploadStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, enum.Enum):
    probe_source = "probe_source"
    analyze = "analyze"  # transcribe (if needed) + AI clip discovery
    render_clip = "render_clip"


class AssetKind(str, enum.Enum):
    source = "source"
    thumbnail = "thumbnail"
    clip = "clip"


class AnalysisStatus(str, enum.Enum):
    queued = "queued"
    transcribing = "transcribing"
    analyzing = "analyzing"
    succeeded = "succeeded"
    failed = "failed"


class CandidateStatus(str, enum.Enum):
    proposed = "proposed"
    selected = "selected"
    rejected = "rejected"


class RenderStatus(str, enum.Enum):
    queued = "queued"
    rendering = "rendering"
    succeeded = "succeeded"
    failed = "failed"


class User(Base, Timestamped):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))


class Project(Base, Timestamped):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus, "project_status"), default=ProjectStatus.uploading, index=True
    )
    status_message: Mapped[str | None] = mapped_column(Text)
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL", use_alter=True, name="fk_projects_source_asset")
    )

    source_asset: Mapped["MediaAsset | None"] = relationship(foreign_keys=[source_asset_id], lazy="raise")
    assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="project", foreign_keys="MediaAsset.project_id", lazy="raise",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    uploads: Mapped[list["UploadSession"]] = relationship(
        back_populates="project", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )


class UploadSession(Base, Timestamped):
    __tablename__ = "upload_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    chunk_size: Mapped[int] = mapped_column(Integer)
    total_chunks: Mapped[int] = mapped_column(Integer)
    received_chunks: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    received_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[UploadStatus] = mapped_column(_enum(UploadStatus, "upload_status"), default=UploadStatus.active)
    staging_path: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="uploads", lazy="raise")


class MediaAsset(Base, Timestamped):
    __tablename__ = "media_assets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AssetKind] = mapped_column(_enum(AssetKind, "asset_kind"))
    storage_backend: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="assets", foreign_keys=[project_id], lazy="raise")
    video_metadata: Mapped["VideoMetadata | None"] = relationship(
        back_populates="asset", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )


class VideoMetadata(Base, Timestamped):
    __tablename__ = "video_metadata"
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True
    )
    container: Mapped[str | None] = mapped_column(String(100))
    duration_s: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    display_width: Mapped[int] = mapped_column(Integer)
    display_height: Mapped[int] = mapped_column(Integer)
    aspect_ratio: Mapped[str] = mapped_column(String(20))
    orientation: Mapped[str] = mapped_column(String(20))
    fps: Mapped[float | None] = mapped_column(Float)
    video_codec: Mapped[str | None] = mapped_column(String(50))
    pixel_format: Mapped[str | None] = mapped_column(String(50))
    bit_rate: Mapped[int | None] = mapped_column(BigInteger)
    has_audio: Mapped[bool] = mapped_column(Boolean)
    audio_codec: Mapped[str | None] = mapped_column(String(50))
    audio_channels: Mapped[int | None] = mapped_column(Integer)
    audio_sample_rate: Mapped[int | None] = mapped_column(Integer)
    audio_track_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_probe: Mapped[dict] = mapped_column(JSONB)

    asset: Mapped[MediaAsset] = relationship(back_populates="video_metadata", lazy="raise")


class Job(Base, Timestamped):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[JobType] = mapped_column(_enum(JobType, "job_type"))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), default=JobStatus.queued, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    arq_job_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="jobs", lazy="raise")


class Transcript(Base, Timestamped):
    """Word-timestamped transcript of a project's source video. One per (project, requested language)."""

    __tablename__ = "transcripts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requested_language: Mapped[str | None] = mapped_column(String(10))  # None = auto-detect
    language: Mapped[str] = mapped_column(String(10))
    language_probability: Mapped[float | None] = mapped_column(Float)
    engine: Mapped[str] = mapped_column(String(100))  # e.g. "faster-whisper:small"
    duration_s: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    # [{"id": 0, "start": 0.0, "end": 4.7, "text": "...", "words": [{"w": "Halo", "s": 0.0, "e": 0.4, "p": 0.98}]}]
    segments: Mapped[list] = mapped_column(JSONB)


class AnalysisRun(Base, Timestamped):
    __tablename__ = "analysis_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transcripts.id", ondelete="SET NULL"))
    status: Mapped[AnalysisStatus] = mapped_column(_enum(AnalysisStatus, "analysis_status"), default=AnalysisStatus.queued)
    clip_count: Mapped[int] = mapped_column(Integer)
    min_duration_s: Mapped[float] = mapped_column(Float)
    max_duration_s: Mapped[float] = mapped_column(Float)
    language: Mapped[str | None] = mapped_column(String(10))
    model: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)  # model's note, e.g. why fewer clips than requested
    usage: Mapped[dict | None] = mapped_column(JSONB)


class ClipCandidate(Base, Timestamped):
    __tablename__ = "clip_candidates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    hook: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    transcript_text: Mapped[str] = mapped_column(Text)
    scores: Mapped[dict] = mapped_column(JSONB)  # hook, emotion, value, standalone, retention, shareability (0-10)
    score: Mapped[float] = mapped_column(Float)  # weighted 0-100
    confidence: Mapped[float] = mapped_column(Float)
    editing_style: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[CandidateStatus] = mapped_column(
        _enum(CandidateStatus, "candidate_status"), default=CandidateStatus.proposed
    )


class ClipRender(Base, Timestamped):
    __tablename__ = "clip_renders"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clip_candidates.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_assets.id", ondelete="SET NULL"))
    status: Mapped[RenderStatus] = mapped_column(_enum(RenderStatus, "render_status"), default=RenderStatus.queued)
    settings: Mapped[dict] = mapped_column(JSONB)  # subtitle style, crop mode, resolution...
    crop: Mapped[dict | None] = mapped_column(JSONB)  # how the frame was chosen (faces found, x offset)
    qc: Mapped[dict | None] = mapped_column(JSONB)  # validation of the actual output file
    error: Mapped[str | None] = mapped_column(Text)
