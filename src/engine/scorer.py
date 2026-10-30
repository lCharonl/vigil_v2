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
)

CONTEXT_RULES: tuple[Rule, ...] = (
    rules_context.check_keywords,
    rules_context.check_tld,
    rules_context.check_certificate_authority,
)

DEFAULT_RULES: tuple[Rule, ...] = BRAND_RULES + CONTEXT_RULES


@dataclass(slots=True)
class ScoreResult:
    """Engine verdict for one event.

    Attributes:
        event: Event that was analyzed.
        parsed: Parsed domain.
        score: Sum of the points of all triggered rules.
        reasons: Reasons provided by the rules that returned a non-zero score.
    """

    event: CertEvent
    parsed: ParsedDomain
    score: int = 0
    reasons: list[str] = field(default_factory=list)


class Scorer:
    """Run a parsed domain through every rule and sum the points.

    A rule is a callable ``(ParsedDomain, CertEvent) -> (int, str)``.
    A rule that raises an exception is skipped and logged so that the
    pipeline is never interrupted.

    Args:
        threshold: Minimum score for a domain to be considered suspicious.
        rules: Rules to apply, in order (``DEFAULT_RULES`` by default).
        parser: FQDN parser to use.
    """

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
        """Compute the score of an event.

        Args:
            event: Event coming from the ingestion queue.

        Returns:
            A ``ScoreResult`` holding the total score and the reasons.
        """
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
        """Tell whether the score reaches the alert threshold.

        Args:
            result: Verdict returned by ``evaluate``.

        Returns:
            True if ``result.score >= threshold``.
        """
        return result.score >= self.threshold
