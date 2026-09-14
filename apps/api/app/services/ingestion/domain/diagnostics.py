"""Typed diagnostics emitted while extracting source documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DiagnosticSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class ExtractionDiagnostic:
    """One actionable, page-scoped extraction observation."""

    code: str
    message: str
    severity: DiagnosticSeverity = "warning"
    page_number: int | None = None
    exception_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
