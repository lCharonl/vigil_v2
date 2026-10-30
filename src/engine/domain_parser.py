"""Split an FQDN into root, subdomains and TLD."""

from dataclasses import dataclass

import tldextract


@dataclass(frozen=True, slots=True)
class ParsedDomain:
    """FQDN split into ``subdomain``, ``root`` label and public ``suffix``."""

    fqdn: str
    subdomain: str
    root: str
    suffix: str

    @property
    def registered_domain(self) -> str:
        """Return ``root.suffix``, or an empty string if invalid."""
        if not self.root or not self.suffix:
            return ""
        return f"{self.root}.{self.suffix}"

    @property
    def subdomain_labels(self) -> tuple[str, ...]:
        """Return the subdomain labels, farthest first."""
        return tuple(label for label in self.subdomain.split(".") if label)


class DomainParser:
    """Network-free ``tldextract`` wrapper using the bundled suffix list."""

    def __init__(self) -> None:
        self._extractor = tldextract.TLDExtract(suffix_list_urls=())

    def parse(self, fqdn: str) -> ParsedDomain:
        """Split an FQDN; fields are empty if no public suffix is recognized."""
        result = self._extractor(fqdn)
        return ParsedDomain(
            fqdn=fqdn,
            subdomain=result.subdomain,
            root=result.domain,
            suffix=result.suffix,
        )
