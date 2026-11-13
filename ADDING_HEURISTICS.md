# Adding a heuristic

This guide explains how to add a detection rule to Vigil V2 and plug it into the pipeline.

## 1. Pick the right module

| Module | Use it for | Examples |
|---|---|---|
| `src/engine/rules_brand.py` | Rules that depend on a monitored **brand** | allowlist, typosquatting, homoglyphs |
| `src/engine/rules_context.py` | **Generic** rules, unrelated to a specific brand | keywords, risky TLDs, certificate authority, subdomain depth |

## 2. Signature and return format

Every heuristic follows the `Rule` signature defined in `scorer.py`:

```python
Rule = Callable[[ParsedDomain, CertEvent], tuple[int, str]]
```

**Inputs**

- `parsed: ParsedDomain` (`src/engine/domain_parser.py`):
  - `fqdn`: full name (`login.paypa1-secure.co.uk`)
  - `subdomain`: `login`
  - `root`: `paypa1-secure`
  - `suffix`: `co.uk`
  - `registered_domain`: `paypa1-secure.co.uk`
  - `subdomain_labels`: `("login",)`
- `event: CertEvent` (`src/core/queue_manager.py`): `domain`, `issuer`, `serial`, `is_precert`, `seen_at`.

**Output: a `(score, reason)` tuple**

| Case | Return |
|---|---|
| The rule does not trigger | `(0, "")` |
| The rule triggers | `(points, "short explanation")` |
| Mitigation (e.g. legitimate domain) | `(-points, "explanation")` |

Constraints:

- `score` is an `int`. It is **added** to the total score; it can be negative.
- `reason` is a readable `str` that appears in the `reasons` field of the alert. An empty reason is ignored.
- The function must be **pure, synchronous and fast**: no I/O or network call, since it runs for every domain of the feed.
- A raised exception is caught by the `Scorer` and the rule is skipped for that domain. It is not a control mechanism: return `(0, "")`.

## 3. Write the function

Add the function to `rules_brand.py` or `rules_context.py`, with a docstring (no `#` comments in the project).

```python
def check_subdomain_depth(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Penalize FQDNs with an abnormal number of subdomains.

    Args:
        parsed: Domain split into root, subdomains and TLD.
        event: Originating event (issuer, serial number, type).

    Returns:
        A ``(score, reason)`` tuple. ``(0, "")`` if the depth is normal.
    """
    depth = len(parsed.subdomain_labels)
    if depth >= 4:
        return 20, f"{depth} subdomain levels"
    return 0, ""
```

Even if your rule does not use `event`, keep both parameters: the orchestrator calls every rule the same way.

## 4. Plug it into `scorer.py`

Rules are registered in three tuples at the top of `src/engine/scorer.py`. The `Scorer` walks through them **in order**.

1. Import the module if it is not already imported (`rules_brand` and `rules_context` already are).
2. Add the function to the matching tuple:

```python
CONTEXT_RULES: tuple[Rule, ...] = (
    rules_context.check_keywords,
    rules_context.check_tld,
    rules_context.check_certificate_authority,
    rules_context.check_subdomain_depth,
)
```

`DEFAULT_RULES = BRAND_RULES + CONTEXT_RULES` is recomputed automatically; nothing else needs to change. Neither `main.py` nor the other modules are affected.

To test a reduced rule set, `Scorer` accepts a `rules` parameter:

```python
scorer = Scorer(threshold=20, rules=[rules_context.check_subdomain_depth])
```

## 5. Calibrate and test

The total score is the sum of the points of all rules. A domain triggers an alert when `score >= threshold` (`--threshold`, 50 by default). Choose your points with that threshold in mind: a weak rule (10-20) must be combined with others, a very reliable rule can reach the threshold on its own.

Quick test without network:

```python
from src.core.queue_manager import CertEvent
from src.engine.scorer import Scorer

scorer = Scorer(threshold=0)
event = CertEvent(domain="a.b.c.d.paypa1.xyz", issuer="Let's Encrypt", serial="01", is_precert=False)
result = scorer.evaluate(event)
print(result.score, result.reasons)
```

To validate end to end with a CertStream server, run `python main.py --threshold 0 --verbose` to see every domain go by.

## Checklist

- [ ] Signature `(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]`
- [ ] Returns `(0, "")` when the rule does not apply
- [ ] Complete docstring, no `#` comment
- [ ] No I/O or blocking call
- [ ] Function added to `BRAND_RULES` or `CONTEXT_RULES` in `scorer.py`
- [ ] Points calibrated against the threshold
