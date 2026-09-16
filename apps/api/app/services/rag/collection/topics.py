"""Topic labels with mandatory verification.

Rule-based suggestions seed the labels; only verified assignments may
feed retrieval signals. An unverified topic is metadata, not evidence.
"""

from __future__ import annotations

from dataclasses import replace

from app.services.rag.collection.schemas import CollectedDocument, TopicAssignment

TOPIC_VOCABULARY: tuple[str, ...] = (
    "pkwt",
    "phk",
    "thr",
    "pengupahan",
    "bpjs",
    "k3",
    "serikat_pekerja",
    "hubungan_industrial",
    "alih_daya",
    "tenaga_kerja_asing",
    "waktu_kerja",
)

_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "pkwt": ("pkwt", "kontrak", "waktu tertentu", "kompensasi"),
    "phk": ("phk", "pemutusan hubungan kerja", "pesangon"),
    "thr": ("thr", "tunjangan hari raya"),
    "pengupahan": ("upah", "gaji", "umk", "ump"),
    "bpjs": ("bpjs", "jht", "jkp", "jkk", "jkm", "jaminan sosial"),
    "k3": ("k3", "keselamatan kerja", "kesehatan kerja", "smk3", "bahaya"),
    "serikat_pekerja": ("serikat pekerja", "serikat buruh"),
    "hubungan_industrial": (
        "hubungan industrial",
        "perselisihan",
        "bipartit",
        "mediasi",
        "konsiliasi",
        "arbitrase",
        "phi",
    ),
    "alih_daya": ("alih daya", "outsourcing"),
    "tenaga_kerja_asing": ("tenaga kerja asing",),
    "waktu_kerja": ("waktu kerja", "jam kerja", "lembur", "cuti"),
}


def suggest_topics(title: str, file_name: str = "") -> list[TopicAssignment]:
    """Propose topics from naming hints. Always unverified by construction."""
    haystack = f"{title} {file_name}".lower()
    suggestions = []
    for topic in TOPIC_VOCABULARY:
        if any(hint in haystack for hint in _TOPIC_HINTS[topic]):
            suggestions.append(TopicAssignment(topic=topic, confidence="medium"))
    return suggestions


def verify_topics(
    document: CollectedDocument,
    topics: list[str],
    reviewer: str,
) -> CollectedDocument:
    """Mark topics verified after human review. Unknown topics are refused."""
    unknown = [topic for topic in topics if topic not in TOPIC_VOCABULARY]
    if unknown:
        raise ValueError(f"Unknown topics: {', '.join(unknown)}")
    verified = {topic: True for topic in topics}
    assignments = tuple(
        TopicAssignment(
            topic=assignment.topic,
            confidence="high" if assignment.topic in verified else assignment.confidence,
            verified=assignment.topic in verified,
            verified_by=reviewer if assignment.topic in verified else None,
        )
        for assignment in document.topics
    )
    existing = {assignment.topic for assignment in assignments}
    additions = tuple(
        TopicAssignment(topic=topic, confidence="high", verified=True, verified_by=reviewer)
        for topic in topics
        if topic not in existing
    )
    return replace(document, topics=(*assignments, *additions))


def retrieval_topics(document: CollectedDocument) -> list[str]:
    """Topics safe to use as retrieval signals: verified only."""
    return [assignment.topic for assignment in document.topics if assignment.verified]
