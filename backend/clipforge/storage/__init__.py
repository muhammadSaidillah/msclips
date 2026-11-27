"""Object storage abstraction. Keys are POSIX-style relative paths, e.g. projects/<id>/source.mp4."""

from __future__ import annotations

import asyncio
import shutil
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from clipforge.core.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


class Storage(ABC):
    backend: str

    @abstractmethod
    async def put_file(self, local_path: Path, key: str, content_type: str | None = None) -> int: ...

    @abstractmethod
    async def get_to_file(self, key: str, local_path: Path) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def size(self, key: str) -> int: ...

    def local_path(self, key: str) -> Path | None:
        """Direct filesystem path when the backend is local (lets workers skip a copy)."""
        return None

    async def presigned_url(self, key: str, expires_s: int = 3600) -> str | None:
        return None

    async def check(self) -> None:
        """Raise StorageError if the backend is unusable."""


def _safe_key(key: str) -> str:
    parts = Path(key).parts
    if not key or key.startswith("/") or ".." in parts:
        raise StorageError(f"invalid storage key: {key!r}")
    return key


class LocalStorage(Storage):
    backend = "local"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def local_path(self, key: str) -> Path:
        return self._path(key)

    async def put_file(self, local_path: Path, key: str, content_type: str | None = None) -> int:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        await asyncio.to_thread(shutil.move, str(local_path), str(tmp))
        tmp.replace(dest)
        return dest.stat().st_size

    async def get_to_file(self, key: str, local_path: Path) -> None:
        await asyncio.to_thread(shutil.copyfile, self._path(key), local_path)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    async def check(self) -> None:
        probe = self.root / ".healthcheck"
        try:
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            raise StorageError(f"local storage not writable: {e}") from e


class S3Storage(Storage):
    backend = "s3"

    def __init__(self, s: Settings):
        import boto3

        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
        )

    async def put_file(self, local_path: Path, key: str, content_type: str | None = None) -> int:
        extra = {"ContentType": content_type} if content_type else None
        size = local_path.stat().st_size
        await asyncio.to_thread(self.client.upload_file, str(local_path), self.bucket, _safe_key(key), ExtraArgs=extra)
        local_path.unlink(missing_ok=True)
        return size

    async def get_to_file(self, key: str, local_path: Path) -> None:
        await asyncio.to_thread(self.client.download_file, self.bucket, _safe_key(key), str(local_path))

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=_safe_key(key))

    async def exists(self, key: str) -> bool:
        try:
            await self.size(key)
            return True
        except Exception:
            return False

    async def size(self, key: str) -> int:
        head = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=_safe_key(key))
        return int(head["ContentLength"])

    async def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": _safe_key(key)},
            ExpiresIn=expires_s,
        )

    async def check(self) -> None:
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
        except Exception as e:
            raise StorageError(f"S3 bucket {self.bucket!r} not reachable: {e}") from e


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage(s)
    if s.storage_backend == "local":
        return LocalStorage(s.storage_dir)
    raise StorageError(f"unknown storage backend {s.storage_backend!r}")
