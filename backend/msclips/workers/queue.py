"""Thin wrapper around arq so the API can enqueue without importing worker code."""

from __future__ import annotations

import uuid
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from msclips.core.config import get_settings


class Queue(Protocol):
    async def enqueue_job_task(self, task: str, job_id: uuid.UUID) -> str: ...
    async def ping(self) -> bool: ...


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class ArqQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(redis_settings())
        return self._pool

    async def enqueue_job_task(self, task: str, job_id: uuid.UUID) -> str:
        pool = await self.pool()
        arq_id = f"{task}:{job_id}"
        await pool.enqueue_job(task, str(job_id), _job_id=arq_id)
        return arq_id

    async def ping(self) -> bool:
        pool = await self.pool()
        return bool(await pool.ping())

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


_queue: Queue | None = None


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = ArqQueue()
    return _queue
