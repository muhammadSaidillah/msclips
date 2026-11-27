import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class AnalysisCreate(BaseModel):
    clip_count: int = Field(ge=1, le=30)
    min_duration_s: float = Field(default=20, ge=5, le=180)
    max_duration_s: float = Field(default=60, ge=10, le=180)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")


class CandidateOut(ORM):
    id: uuid.UUID
    rank: int
    title: str
    start_s: float
    end_s: float
    hook: str
    category: str
    reason: str
    transcript_text: str
    scores: dict
    score: float
    confidence: float
    editing_style: str | None
    status: str


class AnalysisRunOut(ORM):
    id: uuid.UUID
    status: str
    clip_count: int
    min_duration_s: float
    max_duration_s: float
    language: str | None
    model: str | None
    error: str | None
    notes: str | None
    created_at: datetime


class TranscriptInfo(ORM):
    id: uuid.UUID
    language: str
    language_probability: float | None
    engine: str
    duration_s: float
    segment_count: int
    word_count: int


class AnalysisState(BaseModel):
    run: AnalysisRunOut | None
    job: JobOut | None
    transcript: TranscriptInfo | None
    candidates: list[CandidateOut]


class CandidateUpdate(BaseModel):
    status: str = Field(pattern=r"^(proposed|selected|rejected)$")


class RenderCreate(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    edit_style: str | None = Field(default=None, description="'auto' or a style id from GET /styles")
    subtitle_style: str | None = Field(default=None, pattern=r"^(bold|clean|karaoke|none)$",
                                       description="Deprecated: use edit_style and captions")
    captions: bool = True
    show_hook: bool = True

    @model_validator(mode="after")
    def _style(self):
        from msclips.media.styles import STYLES

        if self.edit_style is None:
            if self.subtitle_style == "none":
                self.edit_style, self.captions = "clean", False
            else:
                self.edit_style = self.subtitle_style or "auto"
        if self.edit_style != "auto" and self.edit_style not in STYLES:
            raise ValueError(f"Unknown edit_style '{self.edit_style}'.")
        return self


class RenderOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    rank: int
    title: str
    duration_s: float
    status: str
    error: str | None
    settings: dict
    crop: dict | None
    qc: dict | None
    job: JobOut | None
    file_size_bytes: int | None
    filename: str | None
    created_at: datetime
