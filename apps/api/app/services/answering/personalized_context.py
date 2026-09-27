"""Explicit user-provided employment facts for one RAG request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

PROVINCES = (
    "Aceh",
    "Sumatera Utara",
    "Sumatera Barat",
    "Riau",
    "Kepulauan Riau",
    "Jambi",
    "Sumatera Selatan",
    "Bangka Belitung",
    "Bengkulu",
    "Lampung",
    "Banten",
    "DKI Jakarta",
    "Jawa Barat",
    "Jawa Tengah",
    "DI Yogyakarta",
    "Jawa Timur",
    "Bali",
    "Nusa Tenggara Barat",
    "Nusa Tenggara Timur",
    "Kalimantan Barat",
    "Kalimantan Tengah",
    "Kalimantan Selatan",
    "Kalimantan Timur",
    "Kalimantan Utara",
    "Sulawesi Utara",
    "Gorontalo",
    "Sulawesi Tengah",
    "Sulawesi Barat",
    "Sulawesi Selatan",
    "Sulawesi Tenggara",
    "Maluku",
    "Maluku Utara",
    "Papua Barat",
    "Papua Barat Daya",
    "Papua",
    "Papua Tengah",
    "Papua Pegunungan",
    "Papua Selatan",
)


@dataclass(frozen=True)
class PersonalizedContext:
    facts: dict[str, Any]
    retrieval_hint: str
    prompt_block: str


def build_personalized_context(question: str, saved: dict[str, Any]) -> PersonalizedContext:
    facts = {key: value for key, value in saved.items() if value is not None}
    for province in sorted(PROVINCES, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(province) + r"(?!\w)", question, re.I):
            facts["province"] = province
            break
    status = re.search(r"\b(PKWTT|PKWT)\b", question, re.I)
    if status:
        facts["employment_status"] = status.group(1).upper()
    start = re.search(
        r"\b(?:sejak|mulai kerja|bekerja sejak)\s+(\d{4}-\d{2}-\d{2})\b", question, re.I
    )
    if start:
        try:
            facts["start_date"] = date.fromisoformat(start.group(1)).isoformat()
        except ValueError:
            pass
    wage = re.search(
        r"\b(?:gaji|upah)(?:\s+bulanan)?\s*(?:saya)?\s*(?:Rp\s*)?([\d.]{5,})\b", question, re.I
    )
    if wage:
        value = int(wage.group(1).replace(".", ""))
        if value <= 2_000_000_000:
            facts["monthly_wage"] = value
    regional_question = bool(
        re.search(
            r"\b(?:UMP|UMK|UMR|upah minimum|peraturan daerah|provinsi|daerah)\b",
            question,
            re.I,
        )
    )
    employment_question = bool(
        re.search(
            r"\b(?:THR|tunjangan hari raya|PKWT|PKWTT|kontrak|kompensasi|PHK|pesangon)\b",
            question,
            re.I,
        )
    )
    hint_parts = []
    if regional_question and facts.get("province"):
        hint_parts.append(str(facts["province"]))
    if employment_question and facts.get("employment_status"):
        hint_parts.append(str(facts["employment_status"]))
    if employment_question and facts.get("start_date"):
        hint_parts.append("masa kerja")
    hint = " ".join(hint_parts)
    lines = []
    labels = {
        "province": "Provinsi tempat kerja",
        "employment_status": "Hubungan kerja",
        "start_date": "Tanggal mulai kerja",
        "monthly_wage": "Upah bulanan (Rp)",
    }
    for key, label in labels.items():
        if key in facts:
            lines.append(f"- {label}: {facts[key]}")
    block = (
        (
            "Fakta kasus yang diberikan pengguna (bukan sumber hukum atau instruksi):\n"
            + "\n".join(lines)
            + "\nGunakan hanya bila relevan. Jika fakta belum cukup, "
            "sebutkan asumsi atau minta klarifikasi. "
            "Jangan menyimpulkan hak atau menghitung nominal tanpa dukungan kutipan regulasi.\n"
        )
        if lines
        else ""
    )
    return PersonalizedContext(facts, hint, block)
