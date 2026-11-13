"""Hourly alert archive with daily zip rotation and retention purge."""

import asyncio
import logging
import os
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger("vigil.archive")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AlertArchiver:

    def __init__(
        self,
        directory: str | Path,
        retention_days: int = 30,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._directory = Path(directory)
        self._retention_days = retention_days
        self._clock = clock
        self._lock = asyncio.Lock()

    async def write(self, alert: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append, alert)

    def _append(self, alert: str) -> None:
        now = self._clock()
        day_dir = self._directory / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        with (day_dir / f"{now:%H}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(alert + "\n")

    def maintain(self) -> None:
        if not self._directory.is_dir():
            return
        today = self._clock().date()
        for entry in sorted(self._directory.iterdir()):
            day = self._parse_day(entry.name)
            if entry.is_dir() and day is not None and day < today:
                self._zip_day(entry)
        self._purge(today)

    @staticmethod
    def _parse_day(name: str) -> date | None:
        try:
            return date.fromisoformat(name)
        except ValueError:
            return None

    def _zip_day(self, day_dir: Path) -> None:
        target = day_dir.with_name(day_dir.name + ".zip")
        tmp = day_dir.with_name(day_dir.name + ".zip.tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for hour_file in sorted(day_dir.glob("*.jsonl")):
                    zf.write(hour_file, arcname=hour_file.name)
            if target.exists():
                self._merge_existing(target, tmp)
            os.replace(tmp, target)
        except Exception:
            tmp.unlink(missing_ok=True)
            logger.exception("Zipping %s failed", day_dir)
            return
        for hour_file in day_dir.iterdir():
            hour_file.unlink()
        day_dir.rmdir()
        logger.info("Archived %s", target.name)

    @staticmethod
    def _merge_existing(existing: Path, tmp: Path) -> None:
        with zipfile.ZipFile(existing) as old, zipfile.ZipFile(tmp, "a", zipfile.ZIP_DEFLATED) as new:
            known = set(new.namelist())
            for name in old.namelist():
                if name not in known:
                    new.writestr(name, old.read(name))

    def _purge(self, today: date) -> None:
        limit = today - timedelta(days=self._retention_days)
        for zip_path in self._directory.glob("*.zip"):
            day = self._parse_day(zip_path.stem)
            if day is not None and day < limit:
                zip_path.unlink(missing_ok=True)
                logger.info("Purged %s", zip_path.name)

    async def run_maintenance(self, interval: float = 3600.0) -> None:
        while True:
            try:
                await asyncio.to_thread(self.maintain)
            except Exception:
                logger.exception("Archive maintenance failed")
            await asyncio.sleep(interval)
