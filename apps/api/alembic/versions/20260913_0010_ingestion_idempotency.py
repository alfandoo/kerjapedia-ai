"""add stable source and build idempotency constraints

Revision ID: 20260913_0010
Revises: 20260913_0009
Create Date: 2026-09-13
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0010"
down_revision: str | None = "20260913_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _assert_no_duplicate_source_hashes()
    op.add_column("ingestion_builds", sa.Column("metadata_hash", sa.String(64)))
    _backfill_metadata_hashes()
    op.alter_column("ingestion_builds", "metadata_hash", nullable=False)

    op.drop_constraint(
        "uq_ingestion_build_fingerprint",
        "ingestion_builds",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ingestion_build_fingerprint",
        "ingestion_builds",
        [
            "version_id",
            "config_hash",
            "metadata_hash",
            "embedding_model",
            "embedding_revision",
        ],
    )
    # This may fail closed if legacy duplicate source versions exist. The migration
    # deliberately never guesses which legal version should be deleted or merged.
    op.create_unique_constraint(
        "uq_document_versions_source_sha256",
        "document_versions",
        ["sha256"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_document_versions_source_sha256",
        "document_versions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ingestion_build_fingerprint",
        "ingestion_builds",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ingestion_build_fingerprint",
        "ingestion_builds",
        ["version_id", "config_hash", "embedding_model", "embedding_revision"],
    )
    op.drop_column("ingestion_builds", "metadata_hash")


def _backfill_metadata_hashes() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                ib.build_id, d.document_id, d.title, d.short_title,
                d.regulation_type, d.number, d.year, d.issuer, d.topics,
                dv.legal_status, dv.source_url, dv.local_file, dv.size_bytes,
                dv.sha256, dv.verification_status
            FROM ingestion_builds AS ib
            JOIN documents AS d ON d.document_id = ib.document_id
            JOIN document_versions AS dv ON dv.version_id = ib.version_id
            ORDER BY ib.build_id
            """
        )
    ).mappings()
    updates: list[dict[str, str]] = []
    for row in rows:
        local_file = str(row["local_file"])
        payload: dict[str, Any] = {
            "document_id": str(row["document_id"]),
            "title": str(row["title"]),
            "short_title": str(row["short_title"]),
            "regulation_type": str(row["regulation_type"]),
            "number": int(row["number"]),
            "year": int(row["year"]),
            "issuer": str(row["issuer"]),
            "topics": sorted(str(topic) for topic in (row["topics"] or [])),
            "legal_status": str(row["legal_status"]),
            "source_name": "Database registry",
            "source_url": str(row["source_url"]),
            "local_file": local_file,
            "file_name": PurePosixPath(local_file.replace("\\", "/")).name,
            "size_bytes": int(row["size_bytes"]),
            "sha256": str(row["sha256"]),
            "verification_status": str(row["verification_status"]),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        updates.append(
            {
                "build_id": str(row["build_id"]),
                "metadata_hash": hashlib.sha256(
                    canonical.encode("utf-8")
                ).hexdigest(),
            }
        )
        if len(updates) == 1000:
            _write_updates(connection, updates)
            updates.clear()
    if updates:
        _write_updates(connection, updates)


def _assert_no_duplicate_source_hashes() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            """
            SELECT sha256, COUNT(*) AS duplicate_count
            FROM document_versions
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY sha256
            LIMIT 20
            """
        )
    ).mappings().all()
    if duplicates:
        summary = ", ".join(
            f"{row['sha256']} ({row['duplicate_count']} rows)" for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce canonical source identity while duplicate document "
            f"version hashes exist: {summary}. Resolve them explicitly; this "
            "migration will not delete legal records automatically."
        )


def _write_updates(connection: Any, updates: list[dict[str, str]]) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE ingestion_builds
            SET metadata_hash = :metadata_hash
            WHERE build_id = :build_id
            """
        ),
        updates,
    )
