"""Contextual heuristics not tied to a specific brand."""

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import ParsedDomain


def check_keywords(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Spot phishing keywords in the FQDN."""
    return 0, ""
