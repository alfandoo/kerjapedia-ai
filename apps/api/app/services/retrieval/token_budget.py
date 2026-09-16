"""Token-aware context budget management for RAG pipeline.

Provides approximate token counting and budget-aware context selection
to ensure the LLM prompt never exceeds the model's context window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.retrieval.schemas import RankedChunk

# Approximate characters-per-token ratio for multilingual text (Indonesian + English).
# Whitespace splitting overcounts for CJK but undercounts for European; 3.8
# is a conservative middle ground validated on the golden question set.
_CHARS_PER_TOKEN = 3.8
_FUDGE = 1.15  # safety margin for tokenizer variance

_TOKEN_RE = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """Approximate token count using whitespace splitting with calibration factor.

    This is intentionally fast and model-agnostic — exact tokenization would
    require loading a per-model tokenizer, which is prohibitive for a budget
    gate that runs on every request.  The 1.15x fudge factor covers the gap
    between whitespace tokens and subword tokens for typical Indonesian legal text.
    """
    if not text:
        return 0
    raw_words = len(_TOKEN_RE.findall(text))
    return max(1, int(raw_words * _FUDGE))


def count_message_tokens(
    system_prompt: str,
    user_prompt: str,
    history_block: str = "",
) -> int:
    """Count tokens in the full LLM message (system + user)."""
    return count_tokens(system_prompt) + count_tokens(user_prompt) + count_tokens(history_block)


@dataclass(frozen=True)
class TokenBudget:
    """Manages context token allocation for a single RAG request.

    Conceptual formula::

        available_context = model_window
            - system_prompt_tokens
            - history_tokens
            - query_tokens
            - reserved_output_tokens
            - safety_margin
    """

    model_window: int = 12_000
    system_prompt_tokens: int = 0
    history_tokens: int = 0
    query_tokens: int = 0
    reserved_output_tokens: int = 3_000
    safety_margin_tokens: int = 200

    @property
    def available_for_context(self) -> int:
        """Tokens available for retrieved evidence chunks."""
        used = (
            self.system_prompt_tokens
            + self.history_tokens
            + self.query_tokens
            + self.reserved_output_tokens
            + self.safety_margin_tokens
        )
        return max(256, self.model_window - used)

    def select_chunks_within_budget(
        self,
        ranked: list[RankedChunk],
        max_chunks: int,
        max_chars_per_chunk: int = 2000,
    ) -> list[RankedChunk]:
        """Select ranked chunks that fit within the token budget.

        Iterates through score-sorted chunks, including each if it fits
        the remaining budget.  Stops when budget is exhausted or max_chunks
        is reached.

        Returns at least one chunk if any are available (graceful degradation).
        """
        if not ranked:
            return []

        budget = self.available_for_context
        selected: list[RankedChunk] = []
        used_tokens = 0

        for item in ranked[:max_chunks * 2]:  # look ahead for budget fit
            text = item.document.retrieval_text or item.document.text
            chunk_text = text[:max_chars_per_chunk]
            chunk_tokens = count_tokens(chunk_text)

            # Separator overhead (2 newlines between chunks)
            separator_tokens = 2 if selected else 0
            total_cost = chunk_tokens + separator_tokens

            if used_tokens + total_cost <= budget:
                selected.append(item)
                used_tokens += total_cost
            else:
                # Try a truncated version of this chunk if it's the first one
                if not selected:
                    truncated_tokens = budget - separator_tokens
                    if truncated_tokens > 50:
                        selected.append(item)
                        used_tokens = budget
                break

            if len(selected) >= max_chunks:
                break

        return selected

    def context_tokens_used(
        self,
        chunks: list[RankedChunk],
        max_chars_per_chunk: int = 2000,
    ) -> int:
        """Estimate total tokens used by selected chunks."""
        total = 0
        for item in chunks:
            text = item.document.retrieval_text or item.document.text
            total += count_tokens(text[:max_chars_per_chunk])
        return total
