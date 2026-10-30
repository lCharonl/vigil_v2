"""Engine orchestrator: applies the rules and accumulates scores."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from src.core.queue_manager import CertEvent
from src.engine.domain_parser import DomainParser, ParsedDomain
from src.engine import rules_brand, rules_context

logger = logging.getLogger(__name__)

Rule = Callable[[ParsedDomain, CertEvent], tuple[int, str]]

BRAND_RULES: tuple[Rule, ...] = (
    rules_brand.check_allowlist,
    rules_brand.check_typosquatting,
    rules_brand.check_brand_in_subdomain,
)

CONTEXT_RULES: tuple[Rule, ...] = (
    rules_context.check_keywords,
)

DEFAULT_RULES: tuple[Rule, ...] = BRAND_RULES + CONTEXT_RULES


@dataclass(slots=True)
class ScoreResult:
    """Engine verdict: total ``score`` and the ``reasons`` behind it."""

    event: CertEvent
    parsed: ParsedDomain
    score: int = 0
    reasons: list[str] = field(default_factory=list)


class Scorer:
    """Run each rule on a parsed domain and sum the points. Failing rules are logged and skipped."""

    def __init__(
        self,
        threshold: int = 50,
        rules: Sequence[Rule] = DEFAULT_RULES,
        parser: DomainParser | None = None,
    ) -> None:
        self.threshold = threshold
        self._rules = tuple(rules)
        self._parser = parser or DomainParser()

    def evaluate(self, event: CertEvent) -> ScoreResult:
        """Score an event with every rule."""
        parsed = self._parser.parse(event.domain)
        result = ScoreResult(event=event, parsed=parsed)

        for rule in self._rules:
            try:
                points, reason = rule(parsed, event)
            except Exception:
                logger.exception("Rule %s failed on %s", rule.__name__, event.domain)
                continue
            if points == 0:
                continue
            result.score += points
            if reason:
                result.reasons.append(reason)

        return result

    def is_suspicious(self, result: ScoreResult) -> bool:
        """Return True if the score reaches the threshold."""
        return result.score >= self.threshold
