"""Shared queue between network ingestion and the analysis engine."""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CertEvent:
    """One domain extracted from a certificate (lowercase, no wildcard)."""

    domain: str
    issuer: str
    serial: str
    is_precert: bool
    seen_at: float = field(default_factory=time.time)


class QueueManager:
    """Bounded ``asyncio.Queue`` of events; excess events are dropped and counted."""

    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: asyncio.Queue[CertEvent] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def publish(self, event: CertEvent) -> bool:
        """Push an event without blocking; return False if the queue is full."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            return False
        return True

    async def get(self) -> CertEvent:
        """Wait for the next event."""
        return await self._queue.get()

    def task_done(self) -> None:
        """Mark the last retrieved event as processed."""
        self._queue.task_done()

    def qsize(self) -> int:
        """Return the number of pending events."""
        return self._queue.qsize()

    async def join(self) -> None:
        """Wait until all queued events are processed."""
        await self._queue.join()
