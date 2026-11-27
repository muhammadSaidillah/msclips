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


class AssetKind(str, enum.Enum):
    source = "source"
    thumbnail = "thumbnail"


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
