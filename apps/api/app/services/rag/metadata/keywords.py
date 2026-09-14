"""Key-term extraction: indexable substance per chunk.

Operative legal language — parties, obligations, amounts, deadlines —
becomes a searchable field instead of hiding inside raw text. Terms
are lowercased content tokens plus digit tokens (amounts and article
numbers matter most to the verifier).
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")

_STOPWORDS = frozenset(
    "adalah atau dan dari dengan di ini itu ke pada yang untuk baik bila "
    "karena maupun sebagaimana sebesar serta sebagai bahwa dalam oleh pada "
    "agar setiap orang telah sudah akan dapat harus wajib the and or of to "
    "in on at for with by from this that these those not no a an".split()
)

MAX_TERMS = 32


def extract_key_terms(text: str, limit: int = MAX_TERMS) -> list[str]:
    """Distinctive content tokens plus numbers, in order of appearance."""
    seen: list[str] = []
    known: set[str] = set()
    lowered = text.lower()
    for token in _TOKEN_RE.findall(lowered):
        if len(token) <= 3 or token in _STOPWORDS or token in known:
            continue
        known.add(token)
        seen.append(token)
        if len(seen) >= limit:
            break
    for number in _NUMBER_RE.findall(lowered):
        normalized = number.replace(",", ".")
        if normalized not in known:
            known.add(normalized)
            seen.append(normalized)
    return seen


def detect_language(text: str) -> str:
    """Rough Indonesian-vs-English vote for per-chunk tagging."""
    markers_id = {
        "yang", "dan", "dengan", "untuk", "dari", "pada", "adalah", "pekerja",
        "pengusaha", "pasal", "ayat", "undang", "peraturan", "wajib", "berhak",
    }
    markers_en = {
        "the", "and", "with", "for", "from", "employee", "employer",
        "article", "section", "shall", "entitled",
    }
    tokens = set(_TOKEN_RE.findall(text.lower()))
    id_hits = len(tokens & markers_id)
    en_hits = len(tokens & markers_en)
    if en_hits > id_hits:
        return "en"
    return "id"
