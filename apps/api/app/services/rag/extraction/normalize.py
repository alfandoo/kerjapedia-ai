"""Text normalization: Unicode, hyphenation, whitespace.

Operates line-wise and preserves newlines — joining lines is the
structurer's job, not the normalizer's.
"""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def normalize_text(text: str) -> str:
    """NFKC-fold, dehyphenate wrapped lines, collapse whitespace per line.

    Paragraph breaks (blank lines) are preserved — collapsed to a single
    blank line — because the chunker splits on them. Dropping them merges
    paragraphs and inflates chunks past their token target.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.replace("\xa0", " ")
    folded = _ZERO_WIDTH_RE.sub("", folded)
    lines = [_collapse(line) for line in _dehyphenate(folded).splitlines()]
    paragraphs: list[str] = []
    for line in lines:
        if line:
            paragraphs.append(line)
        elif paragraphs and paragraphs[-1]:
            paragraphs.append("")
    return "\n".join(paragraphs).strip()


def _collapse(line: str) -> str:
    return " ".join(line.split())


def _dehyphenate(text: str) -> str:
    """Join a line ending in "-" with a lowercase continuation.

    The hyphen is kept: Indonesian legal text hyphenates reduplications
    ("masing-masing") far more often than it wraps suffixed words, and a
    kept hyphen still tokenizes into both parts. A hyphen before an
    uppercase continuation is a dash — the break is preserved.
    """
    out: list[str] = []
    pending_hyphen = False
    for line in text.splitlines():
        stripped = line.strip()
        if pending_hyphen:
            if stripped[:1].islower():
                out[-1] = out[-1] + stripped
            else:
                out.append(stripped)
            pending_hyphen = False
            continue
        if stripped.endswith("-") and len(stripped) > 1:
            out.append(stripped)
            pending_hyphen = True
        else:
            out.append(line)
    return "\n".join(out)
