from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLIPFORGE_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+asyncpg://clipforge:clipforge@localhost:5432/clipforge"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Storage
    storage_backend: str = "local"  # "local" | "s3"
    data_dir: Path = Path("./data")  # local storage root + upload staging
    s3_endpoint_url: str | None = None
    s3_bucket: str = "clipforge"
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Upload limits
    max_upload_bytes: int = 20 * 1024**3  # 20 GiB
    chunk_size_bytes: int = 8 * 1024**2  # 8 MiB
    allowed_extensions: list[str] = [".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"]
    max_duration_s: float = 4 * 3600

    ffprobe_bin: str = "ffprobe"
    ffmpeg_bin: str = "ffmpeg"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
