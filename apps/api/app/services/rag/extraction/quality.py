"""Page quality: character ratios plus layout sanity.

The key metric is the spacing-fragment ratio: healthy pages wrap into
long lines, broken extraction yields one short fragment per line. Ratios
alone score spaceless text ~1.0, so the fragment check is what routes
scans to OCR.
"""

from __future__ import annotations

import unicodedata

MIN_TEXT_CHARS = 40
OCR_THRESHOLD = 0.65
_FRAGMENT_WORDS = 2
_FRAGMENT_RATIO = 0.6
_MIN_FRAGMENT_LINES = 10


def spacing_fragment_ratio(text: str) -> float:
    """Share of non-empty lines holding at most two words."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < _MIN_FRAGMENT_LINES:
        return 0.0
    fragments = sum(1 for line in lines if len(line.split()) <= _FRAGMENT_WORDS)
    return fragments / len(lines)


def assess_quality(text: str, min_text_chars: int = MIN_TEXT_CHARS) -> tuple[float, list[str]]:
    """Score page text; flags explain every deduction."""
    flags: list[str] = []
    if len(text) < min_text_chars:
        flags.append("insufficient_text")
    compact = "".join(char for char in text if not char.isspace())
    if not compact:
        return 0.0, [*flags, "empty_page"]
    readable = sum(unicodedata.category(char)[0] not in {"C", "Z"} for char in compact)
    readable_ratio = readable / len(compact)
    alnum_ratio = sum(char.isalnum() for char in compact) / len(compact)
    replacement_ratio = compact.count("�") / len(compact)
    if readable_ratio < 0.97:
        flags.append("control_or_unreadable_characters")
    if alnum_ratio < 0.55:
        flags.append("low_alphanumeric_ratio")
    if replacement_ratio > 0.005:
        flags.append("replacement_glyphs")

    length_score = min(1.0, len(text) / max(1, min_text_chars * 3))
    score = (
        (0.25 * length_score)
        + (0.35 * readable_ratio)
        + (0.35 * min(1.0, alnum_ratio / 0.7))
        + (0.05 * max(0.0, 1.0 - (replacement_ratio * 20)))
    )
    if "insufficient_text" in flags:
        score = min(score, 0.6)
    fragment_ratio = spacing_fragment_ratio(text)
    if fragment_ratio > _FRAGMENT_RATIO:
        flags.append("missing_word_spaces")
        score = min(score, 0.6)
    return round(max(0.0, min(score, 1.0)), 4), flags
