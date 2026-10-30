"""Heuristics related to brand impersonation."""

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import ParsedDomain


def check_allowlist(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Recognize known legitimate domains of monitored brands.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (issuer, serial number, type).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if the rule does not apply.
        A negative score may be returned to lower the total score of a
        legitimate domain.
    """
    return 0, ""


def check_typosquatting(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Detect typographic variations of a monitored brand.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (issuer, serial number, type).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if no similarity is found.
    """
    return 0, ""
