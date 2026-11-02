"""Contextual heuristics not tied to a specific brand."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import ParsedDomain
from src.engine.rules_brand import _LABEL_SEPARATORS, is_legit_domain, load_brand_index

KEYWORDS_FILE = Path(__file__).resolve().parents[1] / "data" / "phishing_keywords.yaml"
STRONG_KEYWORD_SCORE = 15
WEAK_KEYWORD_SCORE = 5
COMPOUND_KEYWORD_SCORE = 25
ROOT_MULTIPLIER = 2
MAX_KEYWORD_SCORE = 40


@dataclass(frozen=True, slots=True)
class KeywordIndex:
    """Token weights and compound token sequences built from the keyword file."""

    tokens: dict[str, int]
    compounds: dict[tuple[str, ...], int]
    root_only: frozenset[str]


def _words(section: dict | None) -> list[str]:
    """Flatten the per-language lists of a section, lowercased."""
    return [w.lower() for words in (section or {}).values() for w in words or []]


@lru_cache(maxsize=1)
def load_keyword_index() -> KeywordIndex:
    """Load the keyword file once. Compounds also register their glued form,
    unless it is already a listed keyword ('log-in' does not override 'login')."""
    with KEYWORDS_FILE.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh)

    tokens: dict[str, int] = {}
    for word in _words(document.get("weak")):
        tokens[word] = WEAK_KEYWORD_SCORE
    for word in _words(document.get("strong")):
        tokens[word] = STRONG_KEYWORD_SCORE

    compounds: dict[tuple[str, ...], int] = {}
    for word in _words(document.get("compounds")):
        parts = _tokens(word)
        compounds[parts] = COMPOUND_KEYWORD_SCORE
        tokens.setdefault("".join(parts), COMPOUND_KEYWORD_SCORE)

    root_only = frozenset(_words(document.get("root_only")))
    for word in root_only:
        tokens[word] = WEAK_KEYWORD_SCORE
    return KeywordIndex(tokens, compounds, root_only)


def _tokens(text: str) -> tuple[str, ...]:
    """Split on label separators, lowercase, drop empty tokens and punycode labels."""
    return tuple(
        token
        for label in text.lower().split(".")
        if not label.startswith("xn--")
        for token in _LABEL_SEPARATORS.split(label)
        if token
    )


def _score_part(
    tokens: tuple[str, ...], index: KeywordIndex, in_root: bool
) -> tuple[int, list[str]]:
    """Sum distinct keyword tokens, then contiguous compound sequences.

    Root-only keywords are skipped when ``in_root`` is False.
    """
    found = [
        t
        for t in dict.fromkeys(tokens)
        if t in index.tokens and (in_root or t not in index.root_only)
    ]
    points = sum(index.tokens[t] for t in found)
    for parts, weight in index.compounds.items():
        size = len(parts)
        if any(tokens[i:i + size] == parts for i in range(len(tokens) - size + 1)):
            points += weight
            found.append("-".join(parts))
    return points, found


def check_keywords(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Spot phishing keywords; those in the registered root weigh more."""
    if is_legit_domain(parsed.fqdn, load_brand_index().legit_domains):
        return 0, ""

    index = load_keyword_index()
    root_points, root_found = _score_part(_tokens(parsed.root), index, in_root=True)
    sub_points, sub_found = _score_part(_tokens(parsed.subdomain), index, in_root=False)
    score = min(root_points * ROOT_MULTIPLIER + sub_points, MAX_KEYWORD_SCORE)
    if score == 0:
        return 0, ""

    parts = []
    if root_found:
        parts.append(f"root: {', '.join(root_found)}")
    if sub_found:
        parts.append(f"subdomain: {', '.join(sub_found)}")
    return score, f"phishing keywords in {'; '.join(parts)}"
