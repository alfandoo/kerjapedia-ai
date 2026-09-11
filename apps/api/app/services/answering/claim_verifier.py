from __future__ import annotations

import re

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
    "sehari": "1",
    "semalam": "1",
    "seminggu": "1",
    "sebulan": "1",
    "setahun": "1",
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


def verify_claims_deterministically(
    claims: list[tuple[str, list[str]]],
    citations: list[Citation],
) -> list[GroundedClaim]:
    citation_by_chunk = {citation.chunk_id: citation for citation in citations}
    verified: list[GroundedClaim] = []
    for text, chunk_ids in claims:
        valid_ids = [chunk_id for chunk_id in chunk_ids if chunk_id in citation_by_chunk]
        support_score, numbers_supported, qualifiers_supported = _score_claim(
            text,
            " ".join(citation_by_chunk[item].quote for item in valid_ids),
        )
        chosen_ids = valid_ids

        # Model-selected IDs are hints, not proof. If another already-retrieved
        # citation supports the complete claim substantially better, relink the
        # claim deterministically instead of rejecting a factually grounded answer.
        if not _is_supported(
            chosen_ids,
            support_score,
            numbers_supported,
            qualifiers_supported,
        ):
            for citation in citations:
                candidate_score, candidate_numbers, candidate_qualifiers = _score_claim(
                    text,
                    citation.quote,
                )
                if (
                    candidate_score >= 0.65
                    and candidate_score > support_score
                    and candidate_numbers
                    and candidate_qualifiers
                ):
                    chosen_ids = [citation.chunk_id]
                    support_score = candidate_score
                    numbers_supported = candidate_numbers
                    qualifiers_supported = candidate_qualifiers

        verified.append(
            GroundedClaim(
                text=text,
                cited_chunk_ids=chosen_ids,
                supported=_is_supported(
                    chosen_ids,
                    support_score,
                    numbers_supported,
                    qualifiers_supported,
                ),
                support_score=round(support_score, 4),
            )
        )
    return verified


def _score_claim(claim: str, evidence: str) -> tuple[float, bool, bool]:
    claim_tokens = _content_tokens(claim)
    evidence_tokens = _content_tokens(evidence)
    support_score = (
        len(claim_tokens.intersection(evidence_tokens)) / len(claim_tokens) if claim_tokens else 0.0
    )
    return (
        support_score,
        _numbers(claim).issubset(_numbers(evidence)),
        claim_tokens.intersection(_MATERIAL_QUALIFIERS).issubset(evidence_tokens),
    )


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
