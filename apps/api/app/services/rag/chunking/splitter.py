"""Token estimation and sentence splitting for Indonesian legal text.

The estimator is an approximation (words plus punctuation marks) — honest
about it, and always applied the same way, so budgets are comparable.
Sentence splitting protects legal abbreviations (``No.``, ``Rp.``,
``dkk.``) that a naive period-split would shred.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

# Abbreviations that must not end a sentence. Dots are masked before the
# split and restored afterwards.
_ABBREVIATIONS = (
    r"No", r"UU", r"PP", r"UUD", r"Rp", r"Dr", r"Drs", r"H", r"Hj", r"Ir", r"Br",
    r"S\.H", r"M\.H", r"dkk", r"dll", r"dsb", r"dst", r"sda",
    r"yth", r"an", r"d\.a", r"u\.b", r"u\.p",
)
_ABBR_RE = re.compile(
    r"\b(" + "|".join(sorted(_ABBREVIATIONS, key=len, reverse=True)) + r")\.",
)
_MASK = "\ue000"
_SENTENCE_END_RE = re.compile(r"([.!?]+[”\"]?)\s+(?=[A-Z0-9“\"(])")


def estimate_tokens(text: str) -> int:
    """Approximate token count: words plus detached punctuation marks."""
    return max(1, len(_WORD_RE.findall(text))) if text.strip() else 0


def fits_budget(text: str, max_tokens: int) -> bool:
    """Whether text stays within a hard token budget."""
    return estimate_tokens(text) <= max_tokens


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; single newlines stay inside paragraphs."""
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def split_sentences(text: str) -> list[str]:
    """Split into sentences without breaking protected abbreviations."""
    masked, swaps = _mask_abbreviations(" ".join(text.split()))
    parts = _SENTENCE_END_RE.split(masked)
    sentences: list[str] = []
    for index in range(0, len(parts) - 1, 2):
        sentence = (parts[index] + parts[index + 1]).strip()
        if sentence:
            sentences.append(_unmask(sentence, swaps))
    tail = parts[-1].strip() if len(parts) % 2 == 1 else ""
    if tail:
        sentences.append(_unmask(tail, swaps))
    return [sentence for sentence in sentences if sentence]


def _mask_abbreviations(text: str) -> tuple[str, dict[str, str]]:
    swaps: dict[str, str] = {}

    def _swap(match: re.Match[str]) -> str:
        token = f"{_MASK}{len(swaps)}{_MASK}"
        swaps[token] = match.group(0)
        return token

    return _ABBR_RE.sub(_swap, text), swaps


def _unmask(text: str, swaps: dict[str, str]) -> str:
    for token, original in swaps.items():
        text = text.replace(token, original)
    return text
