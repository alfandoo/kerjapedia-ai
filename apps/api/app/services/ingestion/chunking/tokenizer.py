"""Tokenizer contracts used to enforce real model input limits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TokenSpan:
    start: int
    end: int


class Tokenizer(Protocol):
    """Minimal offset-aware tokenizer required by the chunker."""

    name: str
    revision: str

    def spans(self, text: str) -> tuple[TokenSpan, ...]: ...

    def count(self, text: str) -> int: ...


class RegexTokenizer:
    """Deterministic offset tokenizer for tests and explicitly offline builds."""

    name = "kerjapedia-regex-tokenizer"
    revision = "v1"
    _TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def spans(self, text: str) -> tuple[TokenSpan, ...]:
        return tuple(
            TokenSpan(match.start(), match.end()) for match in self._TOKEN_RE.finditer(text)
        )

    def count(self, text: str) -> int:
        return len(self.spans(text))
