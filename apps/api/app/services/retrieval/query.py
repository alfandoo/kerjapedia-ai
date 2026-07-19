from __future__ import annotations

import re
import unicodedata

from app.services.retrieval.schemas import QueryUnderstanding

TOPIC_KEYWORDS = {
    "pkwt": ["pkwt", "kontrak", "perjanjian kerja waktu tertentu"],
    "phk": ["phk", "pemutusan hubungan kerja", "pesangon"],
    "thr": ["thr", "tunjangan hari raya"],
    "pengupahan": ["upah", "gaji", "upah minimum", "umk", "ump"],
    "bpjs": ["bpjs", "jht", "jkp", "jkk", "jkm", "jaminan sosial"],
    "k3": ["k3", "keselamatan kerja", "kesehatan kerja", "p2k3", "smk3"],
    "serikat_pekerja": ["serikat pekerja", "serikat buruh"],
    "hubungan_industrial": ["hubungan industrial", "perselisihan"],
    "alih_daya": ["alih daya", "outsourcing"],
    "tenaga_kerja_asing": ["tka", "tenaga kerja asing"],
}

INTENT_KEYWORDS = {
    "definition": ["apa itu", "definisi", "pengertian"],
    "duration": ["berapa lama", "durasi", "jangka waktu", "batas maksimal"],
    "eligibility": ["siapa yang berhak", "berhak", "syarat"],
    "procedure": ["cara", "prosedur", "bagaimana"],
    "comparison": ["perbedaan", "beda", "bandingkan"],
    "calculation": ["hitung", "perhitungan", "berapa besar"],
    "status": ["berlaku", "dicabut", "diubah", "status"],
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


def normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query).lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


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


def rewrite_query(query: str) -> list[str]:
    rewritten = [query]
    expanded = query
    for short, long_form in ABBREVIATIONS.items():
        expanded = re.sub(rf"\b{re.escape(short)}\b", long_form, expanded)
    if expanded != query:
        rewritten.append(expanded)
    return rewritten


def extract_filters(query: str, topics: list[str]) -> dict[str, object]:
    filters: dict[str, object] = {}

    article_match = re.search(r"pasal\s+([0-9]+[a-z]?)", query)
    if article_match:
        filters["article"] = f"Pasal {article_match.group(1).upper()}"

    year_match = re.search(r"\b(19[0-9]{2}|20[0-9]{2})\b", query)
    if year_match:
        filters["year"] = int(year_match.group(1))

    if topics:
        filters["topics"] = topics

    return filters


def understand_query(query: str) -> QueryUnderstanding:
    normalized = normalize_query(query)
    topics = detect_topics(normalized)
    intents = detect_intents(normalized)
    rewritten = rewrite_query(normalized)
    filters = extract_filters(normalized, topics)

    return QueryUnderstanding(
        original_query=query,
        normalized_query=normalized,
        rewritten_queries=rewritten,
        detected_topics=topics,
        detected_intents=intents,
        filters=filters,
    )
