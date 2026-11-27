import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from msclips.models import AssetKind, JobStatus, JobType, ProjectStatus, UploadStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(gt=0)
    content_type: str | None = Field(default=None, max_length=200)
    project_name: str | None = Field(default=None, max_length=200)


class UploadOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    content_type: str | None
    size_bytes: int
    chunk_size: int
    total_chunks: int
    received_chunks: list[int]
    received_bytes: int
    status: UploadStatus
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class VideoMetadataOut(ORM):
    container: str | None
    duration_s: float
    width: int
    height: int
    rotation: int
    display_width: int
    display_height: int
    aspect_ratio: str
    orientation: str
    fps: float | None
    video_codec: str | None
    pixel_format: str | None
    bit_rate: int | None
    has_audio: bool
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    audio_track_count: int


class AssetOut(ORM):
    id: uuid.UUID
    kind: AssetKind
    filename: str
    content_type: str | None
    size_bytes: int
    sha256: str | None
    storage_backend: str
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    type: JobType
    status: JobStatus
    progress: float
    stage: str | None
    attempts: int
    max_attempts: int
    error: str | None
    result: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: ProjectStatus
    status_message: str | None
    created_at: datetime
    updated_at: datetime
    has_thumbnail: bool
    source_filename: str | None
    source_size_bytes: int | None
    duration_s: float | None
    width: int | None
    height: int | None
    aspect_ratio: str | None


class ProjectDetail(ProjectSummary):
    source: AssetOut | None
    metadata: VideoMetadataOut | None
    upload: UploadOut | None
    jobs: list[JobOut]


class ProjectList(BaseModel):
    items: list[ProjectSummary]
    total: int
    limit: int
    offset: int


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class UploadStarted(BaseModel):
    upload: UploadOut
    project: ProjectSummary


class CompleteOut(BaseModel):
    upload: UploadOut
    job: JobOut


class DashboardOut(BaseModel):
    project_counts: dict[str, int]
    total_projects: int
    total_source_bytes: int
    total_source_duration_s: float
    active_jobs: int
    recent_projects: list[ProjectSummary]
