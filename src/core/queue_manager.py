"""Shared queue between network ingestion and the analysis engine."""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CertEvent:
    """Normalized event representing one domain extracted from a certificate.

    Attributes:
        domain: Lowercase FQDN, without wildcard prefix or trailing dot.
        issuer: Organization (or CN as fallback) of the issuing authority.
        serial: Certificate serial number.
        is_precert: True if the entry comes from a precertificate.
        seen_at: Unix timestamp of when the event was received.
    """

    domain: str
    issuer: str
    serial: str
    is_precert: bool
    seen_at: float = field(default_factory=time.time)


class QueueManager:
    """Wrap a bounded ``asyncio.Queue`` of ``CertEvent`` objects.

    The CertStream feed can exceed the engine's processing capacity. Rather
    than blocking the WebSocket read loop, excess events are discarded and
    counted in ``dropped``.

    Args:
        maxsize: Maximum queue capacity (0 for unbounded).
    """

    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: asyncio.Queue[CertEvent] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def publish(self, event: CertEvent) -> bool:
        """Push an event without blocking.

        Args:
            event: Event to hand over to the engine.

        Returns:
            True if the event was accepted, False if it was discarded
            because the queue was full.
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            return False
        return True

    async def get(self) -> CertEvent:
        """Wait for and return the next available event."""
        return await self._queue.get()

    def task_done(self) -> None:
        """Signal that the previously retrieved event has been processed."""
        self._queue.task_done()

    def qsize(self) -> int:
        """Return the number of events currently waiting."""
        return self._queue.qsize()

    async def join(self) -> None:
        """Wait until every queued event has been processed."""
        await self._queue.join()
