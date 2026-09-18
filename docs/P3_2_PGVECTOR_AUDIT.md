# P3-2: pgvector Usage Audit

> Addendum 2026-09: Pinecone + self-hosted BGE-M3 terdokumentasi di bawah
> ini sudah dipensiunkan. Production vector store saat ini adalah
> **Upstash Vector** (HYBRID: `open-ai/text-embedding-3-small` + BM25).
> Dokumen ini dipertahankan sebagai arsip keputusan.

## Current State

### Enabled but Not Used
The PostgreSQL `vector` extension is enabled in migration `20260714_0001_ingestion_tables.py`:
```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

However, the `chunk_embeddings` table stores embeddings as **JSONB**, not as vector columns:
```python
op.create_table(
    "chunk_embeddings",
    sa.Column("chunk_id", sa.String(length=160), nullable=False),
    sa.Column("embedding_model", sa.String(length=120), nullable=False),
    sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),  # JSONB, not vector
    ...
)
```

### Production Vector Store
**Pinecone** is the production vector database for similarity search:
- Dense + sparse vectors stored in Pinecone
- JSONB embeddings in PostgreSQL are for metadata/backup only
- No approximate-nearest-neighbor (ANN) index exists in PostgreSQL

## Audit Findings

| Finding | Status | Impact |
|---------|--------|--------|
| pgvector extension enabled | Active | Wasted resources |
| Vector columns in schema | Not present | No vector search capability |
| ANN indexes | Not present | No similarity search |
| Production usage | Pinecone only | pgvector unused |

## Recommendations

### Option 1: Document and Keep (Recommended)
**Action:** Explicitly document Pinecone as the only production vector index.

**Rationale:**
- Pinecone is already production-ready and tested
- No migration needed for existing data
- Clear separation of concerns (PostgreSQL = metadata, Pinecone = vectors)

**Implementation:**
1. Update documentation to clarify Pinecone is the only vector store
2. Add comments in code explaining pgvector is for future use
3. Keep extension enabled for potential future backend

### Option 2: Remove pgvector Extension
**Action:** Remove the unused extension in a future migration.

**Rationale:**
- Reduces confusion in schema
- Cleaner architecture
- No impact on production

**Implementation:**
1. Create migration to drop extension (if no other dependencies)
2. Update documentation
3. Remove references in code

### Option 3: Implement pgvector Backend
**Action:** Implement a deliberate pgvector backend for redundancy.

**Rationale:**
- Backup vector store capability
- Potential for hybrid search
- PostgreSQL-native vector operations

**Implementation:**
1. Add vector columns to `chunk_embeddings`
2. Create ANN indexes
3. Implement pgvector retrieval provider
4. Add to configuration options

## Decision Matrix

| Criteria | Option 1 (Document) | Option 2 (Remove) | Option 3 (Implement) |
|----------|---------------------|-------------------|----------------------|
| Effort | Low | Medium | High |
| Risk | Low | Low | Medium |
| Future flexibility | High | Low | High |
| Production impact | None | None | None |
| Documentation clarity | High | High | High |

## Recommendation

**Choose Option 1: Document and Keep**

**Reasons:**
1. **Low effort** — Only documentation changes needed
2. **No risk** — No code changes, no migrations
3. **Future flexibility** — pgvector available if needed
4. **Clear documentation** — Explicitly states Pinecone is production

## Implementation Steps

1. **Update documentation:**
   - `docs/ARCHITECTURE.md` — Clarify Pinecone is production vector store
   - `docs/DEPLOYMENT.md` — Note pgvector is enabled but unused
   - `README.md` — Remove pgvector from active components list

2. **Add code comments:**
   - `apps/api/alembic/versions/20260714_0001_ingestion_tables.py` — Document extension purpose
   - `apps/api/app/services/ingestion/vector_indexing.py` — Note Pinecone is production

3. **Update architecture diagrams:**
   - Remove pgvector from active vector flow
   - Show Pinecone as sole vector store

## References

- [INGESTION_AUDIT.md](INGESTION_AUDIT.md) — Finding IDX-03
- [INGESTION_TARGET_ARCHITECTURE.md](INGESTION_TARGET_ARCHITECTURE.md) — Architecture decisions
- [ARCHITECTURE.md](ARCHITECTURE.md) — Current architecture diagrams
