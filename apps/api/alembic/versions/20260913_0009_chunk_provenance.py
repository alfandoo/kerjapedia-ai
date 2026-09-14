"""add categorized chunk provenance and integrity fields

Revision ID: 20260913_0009
Revises: 20260911_0008
Create Date: 2026-09-13
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260913_0009"
down_revision: str | None = "20260911_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AYAT_RE = re.compile(r"Ayat\s*\(([^)]+)\)", re.IGNORECASE)


def upgrade() -> None:
    op.add_column("chunks", sa.Column("parent_chunk_id", sa.String(160)))
    op.add_column("chunks", sa.Column("chunk_index", sa.Integer()))
    op.add_column("chunks", sa.Column("legal_node_id", sa.String(200)))
    op.add_column(
        "chunks",
        sa.Column(
            "section_path",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("chunks", sa.Column("content_hash", sa.String(64)))
    op.add_column("chunks", sa.Column("metadata_hash", sa.String(64)))
    op.add_column(
        "chunks",
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT
                chunk_id,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(build_id, version_id)
                    ORDER BY chunk_id
                ) - 1 AS position
            FROM chunks
        )
        UPDATE chunks AS target
        SET chunk_index = ranked.position
        FROM ranked
        WHERE target.chunk_id = ranked.chunk_id
        """
    )
    _backfill_provenance()

    op.alter_column("chunks", "chunk_index", nullable=False)
    op.alter_column("chunks", "content_hash", nullable=False)
    op.alter_column("chunks", "metadata_hash", nullable=False)
    op.create_foreign_key(
        "fk_chunks_parent_chunk_id_chunks",
        "chunks",
        "chunks",
        ["parent_chunk_id"],
        ["chunk_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_chunks_build_chunk_index",
        "chunks",
        ["build_id", "chunk_index"],
    )
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
    # Existing rows are preserved even if historical page metadata is bad;
    # PostgreSQL still enforces this NOT VALID constraint on every new write.
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT ck_chunks_page_range "
        "CHECK (page_start > 0 AND page_end >= page_start) NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT IF EXISTS ck_chunks_page_range")
    op.drop_index("ix_chunks_content_hash", table_name="chunks")
    op.drop_constraint("uq_chunks_build_chunk_index", "chunks", type_="unique")
    op.drop_constraint("fk_chunks_parent_chunk_id_chunks", "chunks", type_="foreignkey")
    for column in (
        "updated_at",
        "created_at",
        "provenance",
        "metadata_hash",
        "content_hash",
        "section_path",
        "legal_node_id",
        "chunk_index",
        "parent_chunk_id",
    ):
        op.drop_column("chunks", column)


def _backfill_provenance() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                c.chunk_id, c.document_id, c.chunk_index, c.chapter, c.section,
                c.article, c.paragraph, c.page_start, c.page_end, c.text,
                c.created_at, c.updated_at,
                d.title, d.regulation_type, d.number,
                dv.version, dv.legal_status, dv.source_url, dv.local_file,
                dv.sha256, d.year,
                ib.parser_version, ib.chunker_version,
                COALESCE(ce.embedding_model, ib.embedding_model, 'unembedded')
                    AS embedding_model
            FROM chunks AS c
            JOIN documents AS d ON d.document_id = c.document_id
            JOIN document_versions AS dv ON dv.version_id = c.version_id
            LEFT JOIN ingestion_builds AS ib ON ib.build_id = c.build_id
            LEFT JOIN chunk_embeddings AS ce ON ce.chunk_id = c.chunk_id
            ORDER BY c.chunk_id
            """
        )
    ).mappings()

    updates: list[dict[str, Any]] = []
    for row in rows:
        content_hash = _content_hash(str(row["text"]))
        bagian, paragraf = _section_parts(row["section"])
        path = [
            value
            for value in (
                row["chapter"],
                bagian,
                paragraf,
                row["article"],
                row["paragraph"],
            )
            if value
        ]
        payload: dict[str, Any] = {
            "schema_version": "chunk-provenance-v1",
            "document": {
                "document_id": row["document_id"],
                "document_type": row["regulation_type"],
                "document_number": row["number"],
                "year": row["year"],
                "document_title": row["title"],
                "regulation_status": row["legal_status"],
                "source_url": row["source_url"],
                "source_file": row["local_file"],
                "file_hash": row["sha256"],
            },
            "structure": {
                "bab": _strip_prefix(row["chapter"], "BAB "),
                "bagian": _strip_prefix(bagian, "Bagian "),
                "paragraf": _strip_prefix(paragraf, "Paragraf "),
                "pasal": _strip_prefix(row["article"], "Pasal "),
                "ayat": _ayat(row["paragraph"]),
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "section_path": path,
                "legal_node_id": None,
            },
            "chunk": {
                "chunk_id": row["chunk_id"],
                "parent_chunk_id": None,
                "chunk_index": row["chunk_index"],
                "content_hash": content_hash,
            },
            "ingestion": {
                "ingestion_version": f"v{row['version']}",
                "parser_version": row["parser_version"] or "legacy-unknown",
                "chunker_version": row["chunker_version"] or "legacy-unknown",
                "embedding_model": row["embedding_model"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            },
        }
        metadata_hash = _metadata_hash(payload)
        payload["chunk"]["metadata_hash"] = metadata_hash
        updates.append(
            {
                "chunk_id": row["chunk_id"],
                "section_path": json.dumps(path, ensure_ascii=False),
                "content_hash": content_hash,
                "metadata_hash": metadata_hash,
                "provenance": json.dumps(payload, ensure_ascii=False),
            }
        )
        if len(updates) == 1000:
            _write_updates(connection, updates)
            updates.clear()
    if updates:
        _write_updates(connection, updates)


def _write_updates(connection: Any, updates: list[dict[str, Any]]) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE chunks
            SET section_path = CAST(:section_path AS jsonb),
                content_hash = :content_hash,
                metadata_hash = :metadata_hash,
                provenance = CAST(:provenance AS jsonb)
            WHERE chunk_id = :chunk_id
            """
        ),
        updates,
    )


def _content_hash(content: str) -> str:
    normalized = unicodedata.normalize("NFC", content)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _metadata_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _section_parts(section: str | None) -> tuple[str | None, str | None]:
    parts = [part.strip() for part in (section or "").split("/") if part.strip()]
    bagian = next((part for part in parts if part.casefold().startswith("bagian ")), None)
    paragraf = next(
        (part for part in parts if part.casefold().startswith("paragraf ")),
        None,
    )
    return bagian, paragraf


def _ayat(paragraph: str | None) -> str | None:
    match = _AYAT_RE.search(paragraph or "")
    return match.group(1).strip() if match else None


def _strip_prefix(value: str | None, prefix: str) -> str | None:
    if not value:
        return None
    return value[len(prefix) :].strip() if value.casefold().startswith(prefix.casefold()) else value
