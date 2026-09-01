from __future__ import annotations

import re

_DOCUMENT_INJECTION_PATTERNS = (
    re.compile(r"\bignore (all )?(previous|prior|system) instructions?\b", re.IGNORECASE),
    re.compile(r"\babaikan (semua )?instruksi (sebelumnya|sistem|di atas)\b", re.IGNORECASE),
    re.compile(r"\b(system prompt|developer message|jailbreak|developer mode)\b", re.IGNORECASE),
    re.compile(
        r"\b(reveal|print|display|ungkap|tampilkan|cetak).{0,32}"
        r"\b(api[- ]?key|password|credential|access token)\b",
        re.IGNORECASE,
    ),
)


def contains_document_prompt_injection(text: str) -> bool:
    normalized = " ".join(text.split())
    return any(pattern.search(normalized) for pattern in _DOCUMENT_INJECTION_PATTERNS)
