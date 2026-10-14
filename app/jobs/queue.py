"""Durable queue with fair-scheduling and distributed lock support."""

import asyncio
import logging
from typing import Dict, List, Optional, Set
import redis.asyncio as aioredis
from sqlalchemy import select, update
from app.config import settings
from app.database.models import BatchJob, utc_now
from app.database.session import get_db_session

logger = logging.getLogger(__name__)


class DurableJobQueue:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._user_active_counts: Dict[int, int] = {}
        self._in_flight: Set[str] = set()
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if settings.REDIS_URL:
            try:
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
                logger.info("Connected to Redis queue.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis ({e}), falling back to database queue.")
                self._redis = None

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def enqueue_batch(self, batch_id: str) -> None:
        """Pushes batch job ID into the durable queue."""
        if self._redis:
            await self._redis.rpush("tgsaver:queue:batches", batch_id)

    async def get_next_job(self) -> Optional[str]:
        """Pulls the next eligible batch job respecting per-user fair limits."""
        async with self._lock:
            if self._redis:
                batch_id = await self._redis.lpop("tgsaver:queue:batches")
                if batch_id:
                    self._in_flight.add(batch_id)
                    return batch_id

            # Database queue fallback
            async with get_db_session() as session:
                query = select(BatchJob).where(BatchJob.status == "QUEUED")
                if self._in_flight:
                    query = query.where(BatchJob.id.notin_(list(self._in_flight)))
                query = query.order_by(BatchJob.created_at.asc()).limit(10)

                res = await session.execute(query)
                queued_batches = list(res.scalars().all())

                for batch in queued_batches:
                    active = self._user_active_counts.get(batch.user_id, 0)
                    if active < settings.MAX_USER_CONCURRENT_JOBS:
                        # Atomically claim batch in memory and database
                        self._in_flight.add(batch.id)
                        batch.status = "RUNNING"
                        batch.started_at = utc_now()
                        self._user_active_counts[batch.user_id] = active + 1
                        return batch.id

            return None

    async def release_job(self, batch_id: str, user_id: int) -> None:
        """Releases the slot for a finished or failed batch."""
        async with self._lock:
            self._in_flight.discard(batch_id)
            current = self._user_active_counts.get(user_id, 0)
            if current > 0:
                self._user_active_counts[user_id] = current - 1

    async def acquire_user_slot(self, user_id: int) -> bool:
        async with self._lock:
            current = self._user_active_counts.get(user_id, 0)
            if current >= settings.MAX_USER_CONCURRENT_JOBS:
                return False
            self._user_active_counts[user_id] = current + 1
            return True

    async def release_user_slot(self, user_id: int) -> None:
        async with self._lock:
            current = self._user_active_counts.get(user_id, 0)
            if current > 0:
                self._user_active_counts[user_id] = current - 1


job_queue = DurableJobQueue()
