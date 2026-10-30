"""Generate typosquatting variants for the brand domains.

Reads ``src/data/brands_legits_domain.yaml`` and writes
``src/data/brands_typosquats.yaml``. Run from the project root.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engine.domain_parser import DomainParser

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "data"
SOURCE_FILE = DATA_DIR / "brands_legits_domain.yaml"
OUTPUT_FILE = DATA_DIR / "brands_typosquats.yaml"

MIN_ROOT_LENGTH = 3
ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789-"
VOWELS = "aeiou"

KEYBOARD_ROWS = {
    "qwerty": ("1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"),
    "azerty": ("1234567890", "azertyuiop", "qsdfghjklm", "wxcvbn"),
}

HOMOGLYPHS = {
    "a": ("4", "а"),
    "b": ("d", "6"),
    "c": ("с",),
    "d": ("b", "cl"),
    "e": ("3", "е"),
    "g": ("q", "9"),
    "h": ("lh",),
    "i": ("1", "l", "і"),
    "l": ("1", "i", "ӏ"),
    "m": ("rn", "nn"),
    "n": ("m", "r"),
    "o": ("0", "о"),
    "p": ("р",),
    "q": ("g",),
    "s": ("5", "z"),
    "t": ("7",),
    "u": ("v",),
    "v": ("u",),
    "w": ("vv",),
    "x": ("х",),
    "z": ("s", "2"),
    "0": ("o",),
    "1": ("l", "i"),
    "5": ("s",),
}

SWAP_TLDS = (
    "com", "net", "org", "co", "io", "info", "biz", "xyz", "top", "online",
    "site", "app", "support", "club", "shop", "live", "store", "tech", "cc",
    "fr", "de", "uk", "us", "ru", "cn", "tk", "ml", "ga", "cf", "gq",
)

PREFIX_TOKENS = ("www", "my", "secure", "login")


def keyboard_neighbors() -> dict[str, set[str]]:
    """Build the QWERTY and AZERTY key adjacency map."""
    neighbors: dict[str, set[str]] = {}
    for rows in KEYBOARD_ROWS.values():
        for r, row in enumerate(rows):
            for c, key in enumerate(row):
                bucket = neighbors.setdefault(key, set())
                bucket.update(row[max(c - 1, 0):c] + row[c + 1:c + 2])
                for other in (r - 1, r + 1):
                    if 0 <= other < len(rows):
                        bucket.update(rows[other][max(c - 1, 0):c + 2])
    return neighbors


NEIGHBORS = keyboard_neighbors()


def to_ascii_label(label: str) -> str:
    """Return the DNS form of a label (punycode if non-ASCII)."""
    if label.isascii():
        return label
    return label.encode("idna").decode("ascii")


def omission(label: str) -> set[str]:
    """Remove one character at a time."""
    return {label[:i] + label[i + 1:] for i in range(len(label))}


def repetition(label: str) -> set[str]:
    """Double one character at a time."""
    return {label[:i] + label[i] + label[i:] for i in range(len(label))}


def transposition(label: str) -> set[str]:
    """Swap each pair of adjacent characters."""
    return {
        label[:i] + label[i + 1] + label[i] + label[i + 2:]
        for i in range(len(label) - 1)
        if label[i] != label[i + 1]
    }


def replacement(label: str) -> set[str]:
    """Replace one character with a neighboring key."""
    out = set()
    for i, ch in enumerate(label):
        for near in NEIGHBORS.get(ch, ()):
            out.add(label[:i] + near + label[i + 1:])
    return out


def insertion(label: str) -> set[str]:
    """Insert a key adjacent to the character at each position."""
    out = set()
    for i, ch in enumerate(label):
        for near in NEIGHBORS.get(ch, ()):
            out.add(label[:i] + near + label[i:])
            out.add(label[:i + 1] + near + label[i + 1:])
    return out


def homoglyph(label: str) -> set[str]:
    """Replace one character with a look-alike (ASCII, multi-char or Unicode)."""
    out = set()
    for i, ch in enumerate(label):
        for look in HOMOGLYPHS.get(ch, ()):
            out.add(label[:i] + look + label[i + 1:])
    return out


def hyphenation(label: str) -> set[str]:
    """Insert a hyphen between every pair of characters."""
    return {label[:i] + "-" + label[i:] for i in range(1, len(label))}


def vowel_swap(label: str) -> set[str]:
    """Replace one vowel with another vowel."""
    out = set()
    for i, ch in enumerate(label):
        if ch in VOWELS:
            out.update(label[:i] + v + label[i + 1:] for v in VOWELS if v != ch)
    return out


def bitsquatting(label: str) -> set[str]:
    """Flip one bit of one character, keeping only valid hostname characters."""
    out = set()
    for i, ch in enumerate(label):
        for bit in range(8):
            flipped = chr(ord(ch) ^ (1 << bit))
            if flipped in ALPHABET:
                out.add(label[:i] + flipped + label[i + 1:])
    return out


def prefix_tokens(label: str) -> set[str]:
    """Glue a common token in front of the label, with or without hyphen."""
    out = set()
    for token in PREFIX_TOKENS:
        out.add(token + label)
        out.add(f"{token}-{label}")
    return out


LABEL_TECHNIQUES = {
    "omission": omission,
    "repetition": repetition,
    "transposition": transposition,
    "replacement": replacement,
    "insertion": insertion,
    "homoglyph": homoglyph,
    "hyphenation": hyphenation,
    "vowel_swap": vowel_swap,
    "bitsquatting": bitsquatting,
    "prefix_token": prefix_tokens,
}


def is_valid_label(label: str) -> bool:
    """Check hostname label validity (3-63 chars, no edge hyphen)."""
    if not MIN_ROOT_LENGTH <= len(label) <= 63:
        return False
    if label[0] == "-" or label[-1] == "-":
        return False
    return all(c.isalnum() or c == "-" for c in label if c.isascii())


def split_registered(parser: DomainParser, domain: str) -> tuple[str, str]:
    """Split a domain into ``(root, suffix)``, falling back to the last dot."""
    parsed = parser.parse(domain)
    if parsed.root and parsed.suffix:
        return parsed.root, parsed.suffix
    labels = domain.split(".")
    return labels[-2], labels[-1]


def build_variants(root: str, suffix: str) -> dict[str, set[str]]:
    """Return the variant domains of ``root.suffix`` grouped by technique."""
    variants: dict[str, set[str]] = {}
    for name, technique in LABEL_TECHNIQUES.items():
        labels = {to_ascii_label(v) for v in technique(root)}
        variants[name] = {f"{v}.{suffix}" for v in labels if is_valid_label(v)}
    variants["tld_swap"] = {f"{root}.{t}" for t in SWAP_TLDS if t != suffix}
    variants["dot_insertion"] = {
        f"{root[:i]}.{root[i:]}.{suffix}" for i in range(1, len(root))
    }
    return variants


def main() -> None:
    """Read the referential, generate the variants and write the YAML file."""
    parser = DomainParser()
    with SOURCE_FILE.open(encoding="utf-8") as fh:
        brands = yaml.safe_load(fh)["brands"]

    legit: set[str] = set()
    owners: dict[str, list[str]] = {}
    for entry in brands:
        for domain in entry.get("domains") or []:
            root, suffix = split_registered(parser, domain.lower())
            registered = f"{root}.{suffix}"
            legit.add(domain.lower())
            legit.add(registered)
            names = owners.setdefault(registered, [])
            if entry["brand"] not in names:
                names.append(entry["brand"])

    seen_global: dict[str, str] = {}
    result = []
    skipped = []
    for registered in sorted(owners):
        root, suffix = registered.split(".", 1)
        if len(root) < MIN_ROOT_LENGTH:
            skipped.append(registered)
            continue
        entry_variants: dict[str, list[str]] = {}
        taken: set[str] = set()
        for technique, values in build_variants(root, suffix).items():
            kept = sorted(v for v in values if v not in legit and v not in taken)
            taken.update(kept)
            if kept:
                entry_variants[technique] = kept
        for v in taken:
            seen_global.setdefault(v, registered)
        result.append(
            {
                "domain": registered,
                "brands": owners[registered],
                "variants": entry_variants,
            }
        )

    document = {
        "version": 1,
        "source": SOURCE_FILE.name,
        "skipped_short_roots": skipped,
        "domains": result,
    }
    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(document, fh, sort_keys=False, allow_unicode=True, width=120)

    total = sum(len(v) for e in result for v in e["variants"].values())
    print(f"{len(result)} domains, {total} variants, {len(seen_global)} unique, {len(skipped)} skipped")


if __name__ == "__main__":
    main()
