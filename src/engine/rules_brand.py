"""Heuristics related to brand impersonation."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import ParsedDomain

BRANDS_FILE = Path(__file__).resolve().parents[1] / "data" / "brands_legits_domain.yaml"
TYPOSQUATS_FILE = Path(__file__).resolve().parents[1] / "data" / "brands_typosquats.yaml"
BRAND_IN_SUBDOMAIN_SCORE = 40
TYPOSQUAT_SCORE = 60
TLD_SWAP_SCORE = 30
MIN_SUBSTRING_LENGTH = 5
MIN_TOKEN_LENGTH = 2

_LABEL_SEPARATORS = re.compile(r"[.\-_]")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True, slots=True)
class BrandIndex:
    """Lookup structures built from the brand referential."""

    names: dict[str, str]
    legit_domains: frozenset[str]
    substring_pattern: re.Pattern | None
    token_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class TyposquatMatch:
    """Official domain, technique and brands behind a typosquatting variant."""

    domain: str
    technique: str
    brands: tuple[str, ...]


def _normalize(text: str) -> str:
    """Lowercase and drop non-alphanumeric characters."""
    return _NON_ALNUM.sub("", text.lower())


@lru_cache(maxsize=1)
def load_brand_index() -> BrandIndex:
    """Load the brand referential once. Short keys only match whole tokens."""
    with BRANDS_FILE.open(encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)["brands"]

    names: dict[str, str] = {}
    legit: set[str] = set()
    for entry in entries:
        key = _normalize(entry["brand"])
        if key:
            names.setdefault(key, entry["brand"])
        legit.update(d.lower() for d in entry.get("domains") or [])

    long_keys = sorted(
        (k for k in names if len(k) >= MIN_SUBSTRING_LENGTH), key=len, reverse=True
    )
    pattern = re.compile("|".join(map(re.escape, long_keys))) if long_keys else None
    short_keys = frozenset(
        k for k in names if MIN_TOKEN_LENGTH <= len(k) < MIN_SUBSTRING_LENGTH
    )
    return BrandIndex(names, frozenset(legit), pattern, short_keys)


@lru_cache(maxsize=1)
def load_typosquat_index() -> dict[str, TyposquatMatch]:
    """Load the generated variants as a variant -> match lookup table."""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with TYPOSQUATS_FILE.open(encoding="utf-8") as fh:
        document = yaml.load(fh, Loader=loader)

    index: dict[str, TyposquatMatch] = {}
    for entry in document["domains"]:
        brands = tuple(entry["brands"])
        for technique, variants in entry["variants"].items():
            match = TyposquatMatch(entry["domain"], technique, brands)
            for variant in variants:
                index.setdefault(variant, match)
    return index


def _is_legit_domain(fqdn: str, legit_domains: frozenset[str]) -> bool:
    """Tell whether an FQDN is, or sits under, an official domain."""
    labels = fqdn.split(".")
    return any(".".join(labels[i:]) in legit_domains for i in range(len(labels)))


def check_allowlist(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Recognize legitimate brand domains; may return a negative score."""
    return 0, ""


def check_typosquatting(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Match the FQDN or a parent domain against known typosquatting variants."""
    if _is_legit_domain(parsed.fqdn, load_brand_index().legit_domains):
        return 0, ""

    variants = load_typosquat_index()
    labels = parsed.fqdn.lower().split(".")
    for i in range(len(labels) - 1):
        candidate = ".".join(labels[i:])
        match = variants.get(candidate)
        if match is None:
            continue
        score = TLD_SWAP_SCORE if match.technique == "tld_swap" else TYPOSQUAT_SCORE
        return (
            score,
            f"typosquatting of {match.domain} ({match.technique}): {candidate}",
        )
    return 0, ""


def check_brand_in_subdomain(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Detect a brand name in the subdomain of an unrelated domain."""
    if not parsed.subdomain:
        return 0, ""

    index = load_brand_index()
    if _is_legit_domain(parsed.fqdn, index.legit_domains):
        return 0, ""

    subdomain = parsed.subdomain.lower()
    candidates: list[str] = []
    if index.substring_pattern is not None:
        joined = _LABEL_SEPARATORS.sub("", subdomain)
        candidates.extend(m.group() for m in index.substring_pattern.finditer(joined))
    tokens = {_normalize(t) for t in _LABEL_SEPARATORS.split(subdomain)}
    candidates.extend(tokens & index.token_keys)

    if not candidates:
        return 0, ""

    best = max(candidates, key=len)
    target = parsed.registered_domain or parsed.fqdn
    return (
        BRAND_IN_SUBDOMAIN_SCORE,
        f"brand '{index.names[best]}' in subdomain of {target}",
    )
