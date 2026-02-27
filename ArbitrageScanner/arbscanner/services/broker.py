from __future__ import annotations

import abc
import asyncio
import json
import logging
from typing import Sequence

from redis.asyncio import Redis

from arbscanner.config import Settings
from arbscanner.models import Opportunity

LOGGER = logging.getLogger(__name__)


class BaseOpportunityBroker(abc.ABC):
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[list[dict[str, object]]]] = []
        self._latest: list[dict[str, object]] = []

    @abc.abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def publish(self, opportunities: Sequence[Opportunity]) -> None:
        raise NotImplementedError

    def subscribe(self) -> asyncio.Queue[list[dict[str, object]]]:
        queue: asyncio.Queue[list[dict[str, object]]] = asyncio.Queue(maxsize=3)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[list[dict[str, object]]]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_latest(self) -> list[dict[str, object]]:
        return self._latest

    async def _fanout(self, payload: list[dict[str, object]]) -> None:
        self._latest = payload
        for queue in list(self._subscribers):
            try:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(payload)
            except asyncio.QueueEmpty:
                queue.put_nowait(payload)
            except Exception:
                LOGGER.exception("Failed to fanout opportunities")


class InMemoryOpportunityBroker(BaseOpportunityBroker):
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, opportunities: Sequence[Opportunity]) -> None:
        payload = [item.to_dict() for item in opportunities]
        await self._fanout(payload)


class RedisOpportunityBroker(BaseOpportunityBroker):
    def __init__(self, redis_url: str, channel: str) -> None:
        super().__init__()
        self.redis_url = redis_url
        self.channel = channel
        self._redis: Redis | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._redis is not None:
            return
        self._stop_event.clear()
        self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._reader_task:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, opportunities: Sequence[Opportunity]) -> None:
        if self._redis is None:
            raise RuntimeError("Redis broker not started")
        payload = [item.to_dict() for item in opportunities]
        raw = json.dumps(payload)
        await self._redis.publish(self.channel, raw)

    async def _reader_loop(self) -> None:
        if self._redis is None:
            return
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.channel)
        try:
            while not self._stop_event.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if not message:
                    await asyncio.sleep(0.05)
                    continue
                try:
                    data = json.loads(message["data"])
                    if isinstance(data, list):
                        await self._fanout(data)
                except json.JSONDecodeError:
                    LOGGER.warning("Invalid JSON payload in redis channel")
        finally:
            await pubsub.unsubscribe(self.channel)
            await pubsub.aclose()


def build_broker(settings: Settings) -> BaseOpportunityBroker:
    if settings.use_redis:
        if not settings.redis_url:
            raise ValueError("BROKER_MODE=redis requires REDIS_URL")
        return RedisOpportunityBroker(settings.redis_url, settings.redis_channel)
    return InMemoryOpportunityBroker()
