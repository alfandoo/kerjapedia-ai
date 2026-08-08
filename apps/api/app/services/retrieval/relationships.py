from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPERSEDING_RELATIONSHIPS = frozenset({"amended_by", "revoked_by", "replaced_by"})


@dataclass(frozen=True)
class RegulationRelationship:
    from_document_id: str
    to_document_id: str
    relationship_type: str
    confidence: str = "unknown"
    notes: str = ""


@dataclass(frozen=True)
class RelationshipIndex:
    superseded_by: dict[str, list[str]] = field(default_factory=dict)
    superseding: dict[str, list[str]] = field(default_factory=dict)


def build_relationship_index(
    relationships: list[RegulationRelationship],
) -> RelationshipIndex:
    superseded_by: dict[str, list[str]] = {}
    superseding: dict[str, list[str]] = {}
    for relationship in relationships:
        if relationship.relationship_type not in SUPERSEDING_RELATIONSHIPS:
            continue
        superseded_by.setdefault(relationship.from_document_id, []).append(
            relationship.to_document_id
        )
        superseding.setdefault(relationship.to_document_id, []).append(
            relationship.from_document_id
        )
    return RelationshipIndex(superseded_by=superseded_by, superseding=superseding)


def document_superseding_ids(
    index: RelationshipIndex,
    document_id: str,
) -> list[str]:
    return list(dict.fromkeys(index.superseded_by.get(document_id, [])))


def load_relationships(manifest_path: Path) -> list[RegulationRelationship]:
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    relationships: list[RegulationRelationship] = []
    for entry in manifest.get("relationships", []):
        try:
            relationships.append(
                RegulationRelationship(
                    from_document_id=str(entry["from_document_id"]),
                    to_document_id=str(entry["to_document_id"]),
                    relationship_type=str(entry.get("relationship_type", "")),
                    confidence=str(entry.get("confidence", "unknown")),
                    notes=str(entry.get("notes", "")),
                )
            )
        except (KeyError, TypeError):
            continue
    return relationships


@lru_cache(maxsize=4)
def relationship_index_for_manifest(manifest_path: Path) -> RelationshipIndex:
    return build_relationship_index(load_relationships(manifest_path))
