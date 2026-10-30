"""Regex whitelist applied before any scoring rule."""

import re
from collections.abc import Iterable
from pathlib import Path

import yaml

WHITELIST_FILE = Path(__file__).resolve().parents[1] / "data" / "whitelist.yaml"


class Whitelist:
    """Set of regexes; a domain matching any of them is never scored.

    Patterns are case-insensitive and applied with ``re.search`` on the FQDN,
    so anchor them (``^``, ``$``) to avoid partial matches.
    """

    def __init__(self, patterns: Iterable[str] = ()) -> None:
        self._patterns = tuple(self._compile(p) for p in patterns)

    @staticmethod
    def _compile(pattern: str) -> re.Pattern:
        """Compile a pattern, raising ``ValueError`` with the pattern on error."""
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid whitelist regex {pattern!r}: {exc}") from exc

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "Whitelist":
        """Build a whitelist from the ``patterns`` list of a YAML file."""
        with Path(path or WHITELIST_FILE).open(encoding="utf-8") as fh:
            document = yaml.safe_load(fh) or {}
        return cls(document.get("patterns") or [])

    def matches(self, fqdn: str) -> bool:
        """Return True if the FQDN matches any whitelist regex."""
        return any(p.search(fqdn) for p in self._patterns)

    def __len__(self) -> int:
        return len(self._patterns)
