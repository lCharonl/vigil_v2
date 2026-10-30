"""Alert delivery to the terminal or a file."""

import asyncio
import sys
from pathlib import Path


class AlertDispatcher:
    """Write formatted alerts to standard output and/or a file.

    File writes are delegated to a thread so the event loop is never
    blocked. The file format is JSON Lines (one alert per line, appended).

    Args:
        file_path: Output file path, or None to disable file output.
        to_terminal: Enable printing to standard output.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        to_terminal: bool = True,
    ) -> None:
        self._file_path = Path(file_path) if file_path else None
        self._to_terminal = to_terminal
        self._lock = asyncio.Lock()

    async def dispatch(self, alert: str) -> None:
        """Emit an alert to every configured output.

        Args:
            alert: Already formatted alert (a single line of text).
        """
        if self._to_terminal:
            print(alert, file=sys.stdout, flush=True)
        if self._file_path is not None:
            async with self._lock:
                await asyncio.to_thread(self._append, alert)

    def _append(self, alert: str) -> None:
        """Append one line to the end of the output file.

        Args:
            alert: Already formatted alert (a single line of text).
        """
        with self._file_path.open("a", encoding="utf-8") as fh:
            fh.write(alert + "\n")
