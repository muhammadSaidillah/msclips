import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="msclips-test-"))
os.environ.setdefault(
    "MSCLIPS_DATABASE_URL", "postgresql+asyncpg://msclips:msclips@localhost:5432/msclips_test"
)
os.environ["MSCLIPS_DATA_DIR"] = str(_TMP / "data")
os.environ["MSCLIPS_STORAGE_BACKEND"] = "local"
os.environ["MSCLIPS_CHUNK_SIZE_BYTES"] = str(64 * 1024)
os.environ.setdefault("MSCLIPS_WHISPER_MODEL", "tiny")  # small + fast for tests
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import httpx  # noqa: E402
import pytest  # noqa: E402

from msclips.api.main import create_app  # noqa: E402
from msclips.core.db import dispose_engine, get_engine  # noqa: E402
from msclips.models import Base  # noqa: E402
from msclips.workers import queue as queue_mod  # noqa: E402


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
    if shutil.which("espeak-ng"):
        text = (
            "Halo semuanya, selamat datang di podcast kita. Hari ini kita membahas cara memulai bisnis kecil. "
            "Tips pertama, kenali pelanggan kamu sebelum menjual apa pun. Ajak mereka ngobrol dan dengarkan. "
            "Tips kedua, pisahkan uang pribadi dan uang usaha sejak hari pertama. "
            "Ini alasan nomor satu kenapa banyak usaha kecil bangkrut. "
            "Terakhir, konsisten itu kunci. Terima kasih sudah mendengarkan."
        )
        subprocess.run(["espeak-ng", "-v", "id", "-s", "150", "-w", str(d / "speech.wav"), text], check=True)
        _ffmpeg(
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=60", "-i", str(d / "speech.wav"),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
            "-shortest", str(d / "talk.mp4"),
        )
    return d
