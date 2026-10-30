"""Split an FQDN into root, subdomains and TLD."""

from dataclasses import dataclass

import tldextract


@dataclass(frozen=True, slots=True)
class ParsedDomain:
    """Structured result of an FQDN analysis.

    Attributes:
        fqdn: Full domain name that was analyzed.
        subdomain: Part to the left of the root domain (e.g. ``login.secure``).
        root: Root domain label (e.g. ``paypal`` for ``paypal.com``).
        suffix: Public suffix / TLD (e.g. ``com`` or ``co.uk``).
    """

    fqdn: str
    subdomain: str
    root: str
    suffix: str

    @property
    def registered_domain(self) -> str:
        """Registrable domain, i.e. ``root.suffix`` (empty if invalid)."""
        if not self.root or not self.suffix:
            return ""
        return f"{self.root}.{self.suffix}"

    @property
    def subdomain_labels(self) -> tuple[str, ...]:
        """Subdomain labels, from farthest to closest to the root."""
        return tuple(label for label in self.subdomain.split(".") if label)


class DomainParser:
    """Network-free wrapper around ``tldextract``.

    The extractor uses the bundled public suffix list so that it never
    blocks the event loop with a synchronous HTTP request.
    """

    def __init__(self) -> None:
        self._extractor = tldextract.TLDExtract(suffix_list_urls=())

    def parse(self, fqdn: str) -> ParsedDomain:
        """Split an FQDN.

        Args:
            fqdn: Full domain name (e.g. ``login.paypal-secure.xyz``).

        Returns:
            An immutable ``ParsedDomain``. Fields are empty when the name
            has no recognized public suffix.
        """
        result = self._extractor(fqdn)
        return ParsedDomain(
            fqdn=fqdn,
            subdomain=result.subdomain,
            root=result.domain,
            suffix=result.suffix,
        )
