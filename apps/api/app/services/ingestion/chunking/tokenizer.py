"""Tokenizer contracts used to enforce real model input limits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


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


class HuggingFaceTokenizer:
    """Lazy BGE-M3 tokenizer adapter for production ingestion."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        revision: str,
    ) -> None:
        if revision.casefold() in {"", "main", "unversioned", "provider-managed"}:
            raise ValueError("A pinned tokenizer revision is required for reproducible chunking")
        self.name = model_name
        self.revision = revision
        self._instance: Any | None = None

    def spans(self, text: str) -> tuple[TokenSpan, ...]:
        encoded = self._load()(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        return tuple(
            TokenSpan(int(start), int(end))
            for start, end in encoded["offset_mapping"]
            if int(end) > int(start)
        )

    def count(self, text: str) -> int:
        return len(self.spans(text))

    def _load(self) -> Any:
        if self._instance is None:
            try:
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for BGE-M3 token-aware chunking"
                ) from exc
            self._instance = AutoTokenizer.from_pretrained(
                self.name,
                revision=self.revision,
                use_fast=True,
            )
            if not self._instance.is_fast:
                raise RuntimeError("The configured tokenizer must provide character offsets")
        return self._instance


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
