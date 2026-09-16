from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.answering.schemas import Citation, GroundedClaim

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_STOPWORDS = {
    "adalah",
    "atau",
    "dan",
    "dari",
    "dengan",
    "di",
    "ini",
    "itu",
    "ke",
    "pada",
    "yang",
    "untuk",
    "baik",
    "bila",
    "karena",
    "maupun",
    "sebagaimana",
    "sebesar",
    "serta",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
}
_TOKEN_ALIASES = {
    "dilakukan": "laku",
    "melakukan": "laku",
    "mengalami": "alami",
    "kerugian": "rugi",
    "penutupan": "tutup",
}
# Indonesian legal texts spell numbers out ("tujuh hari") while generated
# answers use digits ("7 hari"). Normalize words to digits before comparing
# number sets so factually identical quantities are not flagged unsupported.
_NUMBER_WORDS = {
    "nol": "0",
    "satu": "1",
    "dua": "2",
    "tiga": "3",
    "empat": "4",
    "lima": "5",
    "enam": "6",
    "tujuh": "7",
    "delapan": "8",
    "sembilan": "9",
    "sepuluh": "10",
    "sebelas": "11",
    "dua belas": "12",
    "tiga belas": "13",
    "empat belas": "14",
    "lima belas": "15",
    "enam belas": "16",
    "tujuh belas": "17",
    "delapan belas": "18",
    "sembilan belas": "19",
    "dua puluh": "20",
    "tiga puluh": "30",
    "empat puluh": "40",
    "lima puluh": "50",
    "enam puluh": "60",
    "tujuh puluh": "70",
    "delapan puluh": "80",
    "sembilan puluh": "90",
    "seratus": "100",
    "seribu": "1000",
    "setengah": "0.5",
}
_NUMBER_WORD_PATTERN = re.compile(
    "|".join(
        rf"\b{re.escape(phrase)}\b"
        for phrase in sorted(_NUMBER_WORDS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)
_MATERIAL_QUALIFIERS = {
    "berkelanjutan",
    "berturut",
    "maksimal",
    "minimal",
    "paling",
    "sebelum",
    "setelah",
    "tanpa",
    "tidak",
}


# Citation identifier fields whose numbers are source references, not factual
# assertions: the model is expected to name the cited rule inline
# ("... (UU 6/2023 Pasal 154A huruf b)"), so those digits must not fail the
# numbers-subset gate even when the quoted passage omits them. Page numbers
# and scores are excluded: a bare page digit in prose is not a citation.
_METADATA_NUMBER_FIELDS = (
    "document_id",
    "document_title",
    "short_title",
    "chapter",
    "section",
    "article",
    "paragraph",
)


def _metadata_numbers(citation: Citation) -> set[str]:
    numbers: set[str] = set()
    for field_name in _METADATA_NUMBER_FIELDS:
        value = getattr(citation, field_name, None)
        if value:
            numbers.update(_numbers(str(value)))
    return numbers


def verify_claims_deterministically(
    claims: list[tuple[str, list[str]]],
    citations: list[Citation],
    *,
    query: str | None = None,
) -> list[GroundedClaim]:
    """Score each claim against its cited quotes.

    Numbers already present in the user query are user-supplied facts, not
    model inventions, so they never fail the numbers-subset gate. The same
    holds for numbers from the cited citations' own identifiers (document
    ID, title, article): a claim naming its source inline
    ("... (UU 6/2023 Pasal 154A)") references verifiable metadata, it does
    not invent a quantity. Computed results (e.g. "setengah" from 6/12)
    must still appear in the evidence or be rephrased using the source's
    literal numbers.
    """
    query_numbers = _numbers(query) if query else set()
    citation_by_chunk = {citation.chunk_id: citation for citation in citations}
    metadata_by_chunk = {
        chunk_id: _metadata_numbers(citation)
        for chunk_id, citation in citation_by_chunk.items()
    }
    verified: list[GroundedClaim] = []
    for text, chunk_ids in claims:
        valid_ids = [chunk_id for chunk_id in chunk_ids if chunk_id in citation_by_chunk]
        metadata_numbers = set().union(
            *(metadata_by_chunk[item] for item in valid_ids)
        )
        evaluation = _evaluate_claim_text(
            text,
            " ".join(citation_by_chunk[item].quote for item in valid_ids),
            query_numbers=query_numbers,
            metadata_numbers=metadata_numbers,
        )
        chosen_ids = valid_ids

        # Model-selected IDs are hints, not proof. If another already-retrieved
        # citation supports the complete claim substantially better, relink the
        # claim deterministically instead of rejecting a factually grounded answer.
        if not _is_supported(
            chosen_ids,
            evaluation.support_score,
            evaluation.numbers_ok,
            evaluation.qualifiers_ok,
        ):
            for citation in citations:
                candidate = _evaluate_claim_text(
                    text,
                    citation.quote,
                    query_numbers=query_numbers,
                    metadata_numbers=metadata_by_chunk[citation.chunk_id],
                )
                if (
                    candidate.support_score >= 0.65
                    and candidate.support_score > evaluation.support_score
                    and candidate.numbers_ok
                    and candidate.qualifiers_ok
                ):
                    chosen_ids = [citation.chunk_id]
                    evaluation = candidate

        supported = _is_supported(
            chosen_ids,
            evaluation.support_score,
            evaluation.numbers_ok,
            evaluation.qualifiers_ok,
        )
        verified.append(
            GroundedClaim(
                text=text,
                cited_chunk_ids=chosen_ids,
                supported=supported,
                support_score=round(evaluation.support_score, 4),
                support_detail=_format_support_detail(
                    chosen_ids, evaluation, supported
                ),
            )
        )
    return verified


def _is_supported(
    chunk_ids: list[str],
    support_score: float,
    numbers_supported: bool,
    qualifiers_supported: bool,
) -> bool:
    # Token overlap only needs to show the claim is about the cited rule
    # (~1/3 shared substantive words); legal precision is enforced by the
    # numbers-subset and material-qualifier gates, which stay strict. A higher
    # overlap bar rejects factually correct claims that paraphrase the source
    # ("berhak menerima" vs "wajib memberikan").
    return bool(chunk_ids and numbers_supported and qualifiers_supported and support_score >= 0.35)


@dataclass(frozen=True)
class _ClaimEvaluation:
    support_score: float
    numbers_ok: bool
    qualifiers_ok: bool
    missing_numbers: frozenset[str] = field(default_factory=frozenset)
    missing_qualifiers: frozenset[str] = field(default_factory=frozenset)


def _evaluate_claim_text(
    claim: str,
    evidence: str,
    *,
    query_numbers: frozenset[str] | set[str] = frozenset(),
    metadata_numbers: frozenset[str] | set[str] = frozenset(),
) -> _ClaimEvaluation:
    claim_tokens = _content_tokens(claim)
    evidence_tokens = _content_tokens(evidence)
    support_score = (
        len(claim_tokens.intersection(evidence_tokens)) / len(claim_tokens)
        if claim_tokens
        else 0.0
    )
    allowed_numbers = _numbers(evidence) | set(query_numbers) | set(metadata_numbers)
    missing_numbers = frozenset(_numbers(claim) - allowed_numbers)
    missing_qualifiers = frozenset(
        claim_tokens.intersection(_MATERIAL_QUALIFIERS) - evidence_tokens
    )
    return _ClaimEvaluation(
        support_score=support_score,
        numbers_ok=not missing_numbers,
        qualifiers_ok=not missing_qualifiers,
        missing_numbers=missing_numbers,
        missing_qualifiers=missing_qualifiers,
    )


def _format_support_detail(
    chunk_ids: list[str],
    evaluation: _ClaimEvaluation,
    supported: bool,
) -> str:
    """Compact gate breakdown for logs and repair feedback."""
    if not chunk_ids:
        return "no_cited_chunk"
    if supported:
        return f"overlap={evaluation.support_score:.2f}; gates_ok"
    reasons = [f"overlap={evaluation.support_score:.2f}"]
    if evaluation.support_score < 0.35:
        reasons.append("overlap_below_0.35")
    if not evaluation.numbers_ok:
        missing = ",".join(sorted(evaluation.missing_numbers))
        reasons.append(f"numbers_missing={{{missing}}}")
    if not evaluation.qualifiers_ok:
        missing = ",".join(sorted(evaluation.missing_qualifiers))
        reasons.append(f"qualifiers_missing={{{missing}}}")
    return "; ".join(reasons)


def claim_coverage_score(answer: str, claims: list[GroundedClaim]) -> float:
    answer_tokens = _content_tokens(answer)
    if not answer_tokens or not claims:
        return 0.0
    claim_tokens: set[str] = set()
    for claim in claims:
        claim_tokens.update(_content_tokens(claim.text))
    return round(len(answer_tokens.intersection(claim_tokens)) / len(answer_tokens), 4)


def _content_tokens(value: str) -> set[str]:
    normalized = value.lower()
    normalized = re.sub(r"\bpemutusan\s+hubungan\s+kerja\b", "phk", normalized)
    normalized = re.sub(
        r"\btidak\s+diikuti(?:\s+dengan)?\s+penutupan\b",
        "tanpa penutupan",
        normalized,
    )
    return {
        _TOKEN_ALIASES.get(token, token)
        for token in _TOKEN_RE.findall(normalized)
        if len(token) > 2 and token not in _STOPWORDS
    }


def _numbers(value: str) -> set[str]:
    normalized = _NUMBER_WORD_PATTERN.sub(
        lambda match: _NUMBER_WORDS[match.group(0).lower()], value
    )
    return {number.replace(",", ".") for number in _NUMBER_RE.findall(normalized)}
