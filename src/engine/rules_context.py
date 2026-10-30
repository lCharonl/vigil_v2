"""Contextual heuristics not tied to a specific brand."""

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import ParsedDomain


def check_keywords(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Spot keywords typical of phishing in the FQDN.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (issuer, serial number, type).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if no suspicious keyword
        is found.
    """
    return 0, ""


def check_tld(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Assess the risk associated with the domain's TLD.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (issuer, serial number, type).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if the TLD is not
        considered risky.
    """
    return 0, ""


def check_certificate_authority(
    parsed: ParsedDomain, event: CertEvent
) -> tuple[int, str]:
    """Assess the risk associated with the issuing certificate authority.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (the issuer is in ``event.issuer``).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if the issuer is not
        considered suspicious.
    """
    return 0, ""
