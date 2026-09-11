from __future__ import annotations

import re
import unicodedata

from app.services.retrieval.schemas import QueryUnderstanding

TOPIC_KEYWORDS = {
    "pkwt": [
        "pkwt",
        "kontrak",
        "perjanjian kerja waktu tertentu",
        "kompensasi",
        "uang kompensasi",
        "fixed-term contract",
        "fixed term contract",
        "fixed-term worker",
        "fixed term worker",
        "contract worker",
    ],
    "phk": [
        "phk",
        "pemutusan hubungan kerja",
        "pesangon",
        "termination",
        "dismissal",
        "severance",
    ],
    "thr": ["thr", "tunjangan hari raya", "religious holiday allowance"],
    "pengupahan": [
        "upah",
        "gaji",
        "upah minimum",
        "umk",
        "ump",
        "wage",
        "salary",
        "minimum wage",
    ],
    "bpjs": [
        "bpjs",
        "jht",
        "jkp",
        "jkk",
        "jkm",
        "jaminan sosial",
        "employment social security",
    ],
    "k3": [
        "k3",
        "keselamatan kerja",
        "kesehatan kerja",
        "p2k3",
        "smk3",
        "occupational safety",
        "occupational health",
        "workplace safety",
    ],
    "serikat_pekerja": ["serikat pekerja", "serikat buruh", "trade union", "labor union"],
    "hubungan_industrial": [
        "hubungan industrial",
        "perselisihan",
        "industrial relations",
        "labor dispute",
        "labour dispute",
    ],
    "alih_daya": ["alih daya", "outsourcing"],
    "tenaga_kerja_asing": ["tka", "tenaga kerja asing", "foreign worker"],
}

INTENT_KEYWORDS = {
    "definition": ["apa itu", "definisi", "pengertian", "what is", "definition"],
    "duration": ["berapa lama", "durasi", "jangka waktu", "batas maksimal", "how long"],
    "eligibility": ["siapa yang berhak", "berhak", "syarat", "who is eligible", "eligible"],
    "procedure": ["cara", "prosedur", "bagaimana", "how to", "procedure"],
    "comparison": ["perbedaan", "beda", "bandingkan", "difference", "compare"],
    "calculation": ["hitung", "perhitungan", "berapa besar", "berapa", "calculate", "how much"],
    "status": ["berlaku", "dicabut", "diubah", "status", "in force", "revoked", "amended"],
}

ABBREVIATIONS = {
    "pkwt": "perjanjian kerja waktu tertentu",
    "phk": "pemutusan hubungan kerja",
    "thr": "tunjangan hari raya",
    "jht": "jaminan hari tua",
    "jkp": "jaminan kehilangan pekerjaan",
    "jkk": "jaminan kecelakaan kerja",
    "jkm": "jaminan kematian",
    "k3": "keselamatan dan kesehatan kerja",
    "p2k3": "panitia pembina keselamatan dan kesehatan kerja",
    "smk3": "sistem manajemen keselamatan dan kesehatan kerja",
}

DOMAIN_KEYWORDS = {
    "pekerja",
    "karyawan",
    "buruh",
    "pengusaha",
    "ketenagakerjaan",
    "hubungan kerja",
    "perusahaan",
    "kontrak kerja",
    "cuti",
    "lembur",
    "jam kerja",
    "permenaker",
    "worker",
    "employee",
    "employer",
    "employment",
    "labor law",
    "labour law",
    "workplace",
    "leave entitlement",
    "overtime",
    "working hours",
}


def normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for typo, correction in _COMMON_TYPOS.items():
        normalized = re.sub(rf"\b{re.escape(typo)}\b", correction, normalized)
    return normalized


_COMMON_TYPOS = {
    "kompenasasi": "kompensasi",
    "kompesasi": "kompensasi",
    "konpensasi": "kompensasi",
    "karywan": "karyawan",
    "kryawan": "karyawan",
}


def detect_topics(query: str) -> list[str]:
    return [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in query for keyword in keywords)
    ]


def detect_intents(query: str) -> list[str]:
    intents = [
        intent
        for intent, keywords in INTENT_KEYWORDS.items()
        if any(keyword in query for keyword in keywords)
    ]
    return intents or ["general_question"]


def rewrite_query(
    query: str, *, topics: list[str] | None = None, has_regulation: bool = False
) -> list[str]:
    rewritten = [query]
    expanded = query
    for short, long_form in ABBREVIATIONS.items():
        expanded = re.sub(rf"\b{re.escape(short)}\b", long_form, expanded)
    if expanded != query:
        rewritten.append(expanded)

    # Legal compensation is written as "uang kompensasi" in PP 35/2021, while
    # users usually write just "kompensasi". Expand the synonym so dense
    # retrieval and lexical scoring can reach the operative chunks (Pasal 15-17).
    # The PP 35 hint below is a soft retrieval signal (never a hard filter):
    # it fires on the pkwt topic, so "karyawan kontrak" benefits as well.
    if "kompensasi" in expanded and "uang kompensasi" not in expanded:
        compensation_query = expanded.replace("kompensasi", "uang kompensasi")
        if "pkwt" in (topics or []) and not has_regulation:
            compensation_query = f"{compensation_query} PP 35 Tahun 2021"
        if compensation_query not in rewritten:
            rewritten.append(compensation_query)

    timing_terms = {"kapan", "batas waktu", "tenggat"}
    if any(term in query for term in timing_terms):
        timing_query = f"{expanded} paling lambat wajib dibayarkan sebelum batas waktu pembayaran"
        if timing_query not in rewritten:
            rewritten.append(timing_query)
    english_timing_terms = {"when", "deadline", "due date", "latest payment date"}
    if any(term in query for term in english_timing_terms):
        timing_query = f"{expanded} statutory payment deadline no later than due date"
        if timing_query not in rewritten:
            rewritten.append(timing_query)
    return rewritten


# Named laws laypeople cite instead of numbers. Applied only when no
# explicit regulation was written; explicit codes always win. Deliberately
# narrow: bare "ketenagakerjaan" is too generic to hard-filter on.
_REGULATION_ALIASES: tuple[tuple[str, str, int, int], ...] = (
    (r"\bcipta\s+kerja\b", "UU", 6, 2023),
    (r"\buu\s+ketenagakerjaan\b", "UU", 13, 2003),
    (r"\bundang[\s-]+undang\s+ketenagakerjaan\b", "UU", 13, 2003),
)

_DOCUMENT_ID_RE = re.compile(r"^(UU|PP|PERMENAKER|PERPRES)-(\d+)-(\d{4})$", re.IGNORECASE)


def extract_filters(query: str, topics: list[str]) -> dict[str, object]:
    filters: dict[str, object] = {}

    article_match = re.search(r"pasal\s+([0-9]+[a-z]?)", query)
    if article_match:
        filters["article"] = f"Pasal {article_match.group(1).upper()}"

    year_match = re.search(r"\b(19[0-9]{2}|20[0-9]{2})\b", query)
    if year_match:
        filters["year"] = int(year_match.group(1))

    regulation_match = re.search(
        r"\b(uu|pp|permenaker|perpres)\s*(?:nomor|no\.?\s*)?(\d+)\b",
        query,
    )
    if regulation_match:
        filters["regulation_type"] = {
            "uu": "UU",
            "pp": "PP",
            "permenaker": "Permenaker",
            "perpres": "Perpres",
        }[regulation_match.group(1)]
        filters["number"] = int(regulation_match.group(2))
    else:
        for pattern, regulation_type, number, year in _REGULATION_ALIASES:
            if re.search(pattern, query):
                filters["regulation_type"] = regulation_type
                filters["number"] = number
                filters["year"] = year
                break

    if re.search(r"\b(dicabut|revoked)\b", query):
        filters["legal_status"] = "revoked"

    if topics:
        filters["inferred_topics"] = topics

    return filters


def inherit_regulation_from_context(
    filters: dict[str, object],
    current_topics: list[str],
    context_topics: tuple[str, ...],
    context_document_ids: tuple[str, ...],
) -> dict[str, object]:
    """Inherit document scope (never the article) from conversation context.

    Follow-ups ("berapa besarnya?") reuse the discussed regulation, but an
    article is often the answer itself, so articles never carry over. Only
    a single unambiguous regulation is inherited, and only when the
    current turn brings no regulation and stays on a compatible topic.
    """
    if "regulation_type" in filters:
        return filters
    if current_topics and not set(current_topics).intersection(context_topics):
        return filters
    candidates = set()
    for document_id in context_document_ids:
        match = _DOCUMENT_ID_RE.match(document_id)
        if match:
            candidates.add(
                (
                    {
                        "uu": "UU",
                        "pp": "PP",
                        "permenaker": "Permenaker",
                        "perpres": "Perpres",
                    }[match.group(1).lower()],
                    int(match.group(2)),
                    int(match.group(3)),
                )
            )
    if len(candidates) != 1:
        return filters
    regulation_type, number, year = next(iter(candidates))
    inherited = dict(filters)
    inherited["regulation_type"] = regulation_type
    inherited["number"] = number
    inherited["year"] = year
    return inherited


def understand_query(
    query: str,
    *,
    retrieval_query: str | None = None,
    context_topics: tuple[str, ...] = (),
    context_document_ids: tuple[str, ...] = (),
    context_articles: tuple[str, ...] = (),
) -> QueryUnderstanding:
    normalized = normalize_query(query)
    normalized_retrieval = normalize_query(retrieval_query or query)
    original_topics = detect_topics(normalized)
    topics = list(dict.fromkeys([*detect_topics(normalized_retrieval), *context_topics]))
    intents = detect_intents(normalized)
    filters = extract_filters(normalized, original_topics)
    filters = inherit_regulation_from_context(
        filters, original_topics, context_topics, context_document_ids
    )
    if (
        "year" in filters
        and "regulation_type" not in filters
        and "article" not in filters
    ):
        # A lone year ("berlaku sejak 2019") describes effective timing, not
        # the enactment year — filtering on it over-narrows. Leave it to
        # text matching instead of a hard filter.
        del filters["year"]
    rewritten = rewrite_query(
        normalized_retrieval,
        topics=topics,
        has_regulation="regulation_type" in filters,
    )

    return QueryUnderstanding(
        original_query=query,
        normalized_query=normalized,
        rewritten_queries=rewritten,
        detected_topics=topics,
        detected_intents=intents,
        filters=filters,
        retrieval_query=retrieval_query or query,
        normalized_retrieval_query=normalized_retrieval,
        context_topics=list(context_topics),
        context_document_ids=list(context_document_ids),
        context_articles=list(context_articles),
    )


def is_employment_query(query: QueryUnderstanding) -> bool:
    if query.detected_topics:
        return True
    candidate = query.normalized_retrieval_query or query.normalized_query
    return any(keyword in candidate for keyword in DOMAIN_KEYWORDS)
