"""Alert formatting."""

import json
from datetime import datetime, timezone

from src.engine.scorer import ScoreResult


class AlertFormatter:
    """Turn a ``ScoreResult`` into a serializable alert."""

    @staticmethod
    def to_dict(result: ScoreResult) -> dict:
        """Build the alert dictionary.

        Args:
            result: Engine verdict for one domain.

        Returns:
            A JSON-compatible dictionary describing the domain, the score,
            the reasons and the certificate metadata.
        """
        event = result.event
        parsed = result.parsed
        return {
            "timestamp": datetime.fromtimestamp(event.seen_at, tz=timezone.utc).isoformat(),
            "domain": event.domain,
            "root": parsed.root,
            "subdomain": parsed.subdomain,
            "tld": parsed.suffix,
            "score": result.score,
            "reasons": result.reasons,
            "issuer": event.issuer,
            "serial": event.serial,
            "cert_type": "PRECERT" if event.is_precert else "X509",
        }

    @classmethod
    def to_json(cls, result: ScoreResult) -> str:
        """Serialize the alert as a single JSON line.

        Args:
            result: Engine verdict for one domain.

        Returns:
            A compact JSON string with no trailing newline.
        """
        return json.dumps(cls.to_dict(result), ensure_ascii=False)
