"""Document structuring: legal lines into hierarchical segments."""

from app.services.rag.structuring.markers import (
    AliasTable,
    Marker,
    apply_aliases,
    detect_marker,
    normalize_marker_line,
)
from app.services.rag.structuring.parser import PageText, parse_segments, parse_segments_report
from app.services.rag.structuring.schemas import (
    LegalSegment,
    SegmentIssue,
)
from app.services.rag.structuring.validate import validate_segments

__all__ = [
    "AliasTable",
    "LegalSegment",
    "Marker",
    "PageText",
    "SegmentIssue",
    "apply_aliases",
    "detect_marker",
    "normalize_marker_line",
    "parse_segments",
    "parse_segments_report",
    "validate_segments",
]
