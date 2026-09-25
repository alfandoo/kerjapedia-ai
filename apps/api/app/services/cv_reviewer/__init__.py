"""CV reviewer boundary — isolated from legal regulation RAG.

Pipeline: CV Upload → Validation → Temporary Storage (Supabase ``cv-tmp/``)
→ Text Extraction → Structured Parser → LLM Review → Result → Retention
Cleanup (TTL 24h).

Security invariants:
- CV bytes are never indexed into the regulation Upstash namespace.
- Raw CV text and PII are never written to structured logs or RAG traces.
- Objects are private; access requires owner/session match + signed URL.
- Retention cleanup deletes the object after review or TTL expiry.
"""

from app.services.cv_reviewer.service import (
    CV_MAX_BYTES,
    CV_TMP_PREFIX,
    validate_cv_upload,
)

__all__ = ["CV_MAX_BYTES", "CV_TMP_PREFIX", "validate_cv_upload"]
