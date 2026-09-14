"""Deterministic Indonesian legal-structure parsing."""

from app.services.ingestion.structure.parser import (
    IndonesianLegalStructureParser,
    parse_legal_sections,
)

__all__ = ["IndonesianLegalStructureParser", "parse_legal_sections"]
