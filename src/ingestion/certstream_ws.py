"""CertStream feed ingestion over WebSocket."""

import asyncio
import json
import logging
import os

import websockets

from src.core.queue_manager import CertEvent, QueueManager

logger = logging.getLogger(__name__)

DEFAULT_URL = os.environ.get("CERTSTREAM_URL", "ws://localhost:8080/")


class CertstreamClient:
    """WebSocket client that publishes one ``CertEvent`` per certificate domain, with auto-reconnect."""

    def __init__(
        self,
        queue: QueueManager,
        url: str = DEFAULT_URL,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._queue = queue
        self._url = url
        self._reconnect_delay = reconnect_delay

    async def run(self) -> None:
        """Ingest forever, reconnecting after each disconnection."""
        while True:
            try:
                await self._consume()
            except (OSError, websockets.ConnectionClosed) as exc:
                logger.warning(
                    "Connection lost (%s), retrying in %ss",
                    exc,
                    self._reconnect_delay,
                )
            await asyncio.sleep(self._reconnect_delay)

    async def _consume(self) -> None:
        """Publish events until the connection drops."""
        async with websockets.connect(self._url) as ws:
            logger.info("Connected to %s", self._url)
            async for raw in ws:
                for event in self.parse_message(raw):
                    self._queue.publish(event)

    @staticmethod
    def clean_domain(domain: str) -> str:
        """Lowercase a domain and strip ``*.`` and the trailing dot."""
        domain = domain.strip().lower().rstrip(".")
        if domain.startswith("*."):
            domain = domain[2:]
        return domain

    @classmethod
    def parse_message(cls, raw: str | bytes) -> list[CertEvent]:
        """Convert a raw message into deduplicated events; empty if invalid or CA."""
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []

        if not isinstance(msg, dict) or msg.get("message_type") != "certificate_update":
            return []

        data = msg.get("data") or {}
        leaf = data.get("leaf_cert") or {}
        if leaf.get("is_ca"):
            return []

        issuer_info = leaf.get("issuer") or {}
        issuer = issuer_info.get("O") or issuer_info.get("CN") or "?"
        serial = str(leaf.get("serial_number", "?"))
        is_precert = data.get("update_type") == "PrecertLogEntry"

        domains = {cls.clean_domain(d) for d in leaf.get("all_domains") or []}
        return [
            CertEvent(domain=d, issuer=issuer, serial=serial, is_precert=is_precert)
            for d in sorted(domains)
            if d
        ]
