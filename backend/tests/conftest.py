import os
import subprocess
import tempfile
import uuid
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="clipforge-test-"))
os.environ.setdefault(
    "CLIPFORGE_DATABASE_URL", "postgresql+asyncpg://clipforge:clipforge@localhost:5432/clipforge_test"
)
os.environ["CLIPFORGE_DATA_DIR"] = str(_TMP / "data")
os.environ["CLIPFORGE_STORAGE_BACKEND"] = "local"
os.environ["CLIPFORGE_CHUNK_SIZE_BYTES"] = str(64 * 1024)

import httpx  # noqa: E402
import pytest  # noqa: E402

from clipforge.api.main import create_app  # noqa: E402
from clipforge.core.db import dispose_engine, get_engine  # noqa: E402
from clipforge.models import Base  # noqa: E402
from clipforge.workers import queue as queue_mod  # noqa: E402


class FakeQueue:
    """Records enqueued work; tests run the task explicitly so results are deterministic."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, uuid.UUID]] = []
        self.fail = False

    async def enqueue_job_task(self, task: str, job_id: uuid.UUID) -> str:
        if self.fail:
            raise ConnectionError("redis down")
        self.enqueued.append((task, job_id))
        return f"{task}:{job_id}"

    async def ping(self) -> bool:
        return not self.fail


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture
def fake_queue():
    q = FakeQueue()
    return q


@pytest.fixture
async def client(fake_queue):
    app = create_app()
    app.dependency_overrides[queue_mod.get_queue] = lambda: fake_queue
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media_dir() -> Path:
    d = _TMP / "media"
    d.mkdir()
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-shortest",
        str(d / "landscape.mp4"),
    )
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=25:duration=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(d / "portrait_noaudio.mov"),
    )
    (d / "corrupt.mp4").write_bytes(os.urandom(300_000))
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", str(d / "audio_only.mp4"),
    )
    return d
