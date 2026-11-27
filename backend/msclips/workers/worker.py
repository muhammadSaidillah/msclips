"""arq worker entry point:  arq msclips.workers.worker.WorkerSettings"""

import logging

from msclips.core.config import get_settings
from msclips.core.db import dispose_engine
from msclips.workers.queue import redis_settings
from msclips.workers.pipeline import analyze, render_clip
from msclips.workers.tasks import probe_source


async def startup(ctx: dict) -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    s.staging_dir.mkdir(parents=True, exist_ok=True)


async def shutdown(ctx: dict) -> None:
    await dispose_engine()


class WorkerSettings:
    functions = [probe_source, analyze, render_clip]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 2  # transcription and rendering are CPU-heavy
    max_tries = 5  # task-level retry accounting lives in the jobs table
    job_timeout = 3600
    keep_result = 3600
