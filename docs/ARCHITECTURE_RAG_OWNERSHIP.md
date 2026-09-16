# RAG Architecture Ownership Boundary

## Overview

This document clarifies the ownership boundary between the legacy `app.services.ingestion` / `app.services.retrieval` / `app.services.answering` packages and the new `app.services.rag` clean-room rewrite.

## Legacy Packages (Production)

### `app.services.ingestion`
**Status:** Production-active, legacy
**Responsibility:** Document ingestion pipeline

**Owned by:**
- `pipeline.py` — Main ingestion orchestrator
- `chunker.py` — Text chunking and segmentation
- `embeddings.py` — Embedding generation
- `vector_indexing.py` — Pinecone vector storage
- `legal_parser.py` — Legal document structure parsing
- `pdf_extractor.py` — PDF text extraction
- `cleaning/` — Text normalization and cleaning
- `schemas.py` — Ingestion data models
- `quality.py` — Quality gate checks
- `release_builder.py` — Release management
- `metadata.py` — Document metadata management
- `file_validation.py` — PDF validation
- `safety.py` — Prompt injection detection

### `app.services.retrieval`
**Status:** Production-active, legacy
**Responsibility:** Query processing and document retrieval

**Owned by:**
- `pinecone_store.py` — Pinecone vector store interface
- `reranker.py` — Heuristic reranking
- `query.py` — Query understanding and rewriting
- `postprocessing.py` — MMR, expansion, deduplication
- `scoring.py` — Score normalization
- `filtering.py` — Legal status filtering
- `relationships.py` — Legal relationship tracking
- `schemas.py` — Retrieval data models
- `token_budget.py` — Token budget management
- `engine.py` — Retrieval engine orchestration
- `governance.py` — Retrieval governance rules

### `app.services.answering`
**Status:** Production-active, legacy
**Responsibility:** Answer generation and citation

**Owned by:**
- `generator.py` — Answer generation
- `openrouter_generator.py` — OpenRouter integration
- `prompts.py` — Prompt templates
- `citations.py` — Citation extraction and formatting
- `schemas.py` — Answer data models

## New RAG Package (Clean-Room Rewrite)

### `app.services.rag`
**Status:** Experimental, clean-room rewrite
**Responsibility:** Next-generation RAG services

**Current scope:**
- Only contains `__init__.py` with documentation
- No active code or entry points
- Intended for future implementation based on audit lessons

**Planned responsibilities:**
1. **Collection Management**
   - Provenance tracking with checksum history
   - Freshness monitoring and staleness detection
   - Version lineage and amendment tracking

2. **Extraction Pipeline**
   - Self-validating output detection
   - Automatic OCR escalation for degraded text
   - Layout-aware parsing with table preservation

3. **Quality Assurance**
   - Guarded destructive operations with audit trails
   - Validation stage with recall probes
   - Automated quality gate enforcement

4. **Release Management**
   - Immutable build artifacts
   - Rollback capabilities
   - Canary deployments

## Ownership Rules

### 1. No Cross-Package Dependencies
The new `app.services.rag` package must NOT import from legacy packages:
```python
# ❌ FORBIDDEN
from app.services.ingestion import ...
from app.services.retrieval import ...
from app.services.answering import ...
```

### 2. Shared External Dependencies
Both packages may import from:
- `app.core.config` — Application settings
- `app.db` — Database models and sessions
- External libraries (Pinecone, OpenAI, etc.)

### 3. Migration Path
When migrating functionality from legacy to new:
1. **Copy, don't import** — Duplicate necessary code
2. **Preserve interfaces** — Maintain API compatibility
3. **Run parallel** — Both packages active during transition
4. **Deprecate gradually** — Mark legacy as deprecated
5. **Remove cleanly** — Delete legacy after migration

### 4. Testing Boundaries
- Legacy packages: Maintain existing test coverage
- New package: Comprehensive tests from day one
- Integration tests: Cross-package validation

## Current State

### Production Dependencies
```
routes_chat.py → RetrievalEngine → PineconeRetrievalStore → AnswerGenerator
     ↓                              ↓                          ↓
  (retrieval)                 (ingestion)               (answering)
```

### Future State
```
routes_chat.py → RAGPipeline → RAGRetrieval → RAGAnswering
     ↓              ↓              ↓              ↓
  (rag)          (rag)          (rag)          (rag)
```

## Decision Record

| Decision | Date | Rationale |
|----------|------|-----------|
| Keep legacy packages active | 2026-09-15 | Production stability, no breaking changes |
| New package as clean-room | 2026-09-15 | Avoid technical debt accumulation |
| No cross-package imports | 2026-09-15 | Clear ownership, testability |
| Parallel operation | 2026-09-15 | Gradual migration, risk mitigation |

## Migration Checklist

- [ ] Audit current usage patterns
- [ ] Define new package interfaces
- [ ] Implement core components
- [ ] Add comprehensive tests
- [ ] Run parallel validation
- [ ] Update documentation
- [ ] Deprecate legacy components
- [ ] Remove legacy code

## References

- [INGESTION_AUDIT.md](INGESTION_AUDIT.md) — Full audit findings
- [INDUSTRY_READINESS_AUDIT.md](audits/INDUSTRY_READINESS_AUDIT.md) — Engineering maturity assessment
- [PRD_KerjaPedia_AI.md](PRD_KerjaPedia_AI.md) — Product requirements
