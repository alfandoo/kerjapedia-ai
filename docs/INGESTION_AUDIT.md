# KerjaPedia AI Ingestion Engineering Audit

> ARCHIVED 2026-09: audit pra-Upstash; referensi Pinecone/BGE-M3 di bawah
> adalah historis. Produksi saat ini: Neon PostgreSQL + Supabase Storage +
> Upstash Vector HYBRID (text-embedding-3-small + BM25). Lihat
> `docs/system-design/` sebagai sumber utama.

**Audit date:** 2026-09-13
**Scope:** Current repository working tree, ingestion-related tests, migrations, configuration, and stored local ingestion artifacts
**Change policy:** Analysis only. This audit does not change the ingestion implementation.

## Executive summary

KerjaPedia AI already has several strong production-oriented foundations: immutable build identifiers, checksummed artifacts, resumable embedding checkpoints, PostgreSQL governance records, advisory locking, human review states, and Pinecone release namespaces that are separate from active retrieval. The active implementation is a custom Python ingestion pipeline; it is not based on LangChain, LlamaIndex, Haystack, or another RAG orchestration framework.

The current pipeline is nevertheless **not ready for unattended production ingestion of Indonesian legal documents**. The most important issue is that build identity does not include source metadata or source-code identity, while the API's forced re-ingestion path always resumes an existing build. A change to title, legal status, source URL, topics, or parser code can therefore reuse artifacts built under older assumptions. For a legal RAG system, that is a release-integrity risk rather than only a cache inconvenience.

The next tier of risk is concentrated in extraction and provenance. The active PyMuPDF path does not reconstruct multi-column order or table contents, OCR is document-wide and can fail open, legal hierarchy is flattened, and chunks retain only segment-wide page ranges. Those limitations can produce plausible text with incomplete or inaccurate citation provenance. Pinecone release isolation reduces serving risk, but the active release builder does not reconcile the expected and stored vector sets after upsert.

The audit found two distinct RAG implementations:

- **Active:** `apps/api/app/services/ingestion/*`, called by CLI, API, Celery, and release-building code.
- **Unwired:** `apps/api/app/services/rag/*`, a newer set of collection, loading, extraction, cleaning, structuring, chunking, embedding, indexing, and validation modules. These modules have unit tests but are not imported by the active application path. Their capabilities are not treated as current production behavior.

Repository evidence at audit time:

- The focused ingestion/RAG component suite passed: **120 passed**.
- The full backend test command stopped at collection because `test_proxy_trust.py` imports a removed `app.main.state` symbol and `app.services.rag.retrieval.consistency` imports itself.
- With those two modules excluded: **353 passed, 44 errors**. Most errors were caused by the configured PostgreSQL test database at `127.0.0.1:5433` being unavailable; one teardown also failed attempting to restore `dataset/metadata.json` in the restricted audit environment.
- `storage/ingestion/documents` contained **19 current build manifests and 4,739 chunks**. Fourteen builds were `completed`; five were `review_required` (`PP-37-2021`, `PP-6-2025`, `UU-1-1970`, `UU-13-2003`, and `UU-6-2023`).
- All inspected current local artifacts used `local-hash-embedding-v1` with 1,024 dimensions, not release-candidate BGE-M3 vectors. They prove artifact generation, not a live production OCR → BGE-M3 → Pinecone execution.

### Severity and priority

| Severity | Priority | Meaning in this audit |
| --- | --- | --- |
| CRITICAL | P0 | Can silently publish stale, incorrect, or irreproducible legal knowledge. |
| HIGH | P1 | Materially harms retrieval quality, provenance, or production reliability. |
| MEDIUM | P2 | Meaningful weakness with a bounded workaround or reduced immediate impact. |
| LOW | P3 | Maintainability, documentation, or defense-in-depth improvement. |

Breaking-change risk describes the likely compatibility risk of the recommended solution, not the severity of the current behavior.

## Current architecture

| Concern | Current implementation |
| --- | --- |
| Frontend | Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, and shadcn/Radix components. The frontend calls backend routes through a Next.js BFF under `/api/backend/*`. |
| Backend | Python 3.12, FastAPI, Pydantic Settings, synchronous SQLAlchemy 2, and Alembic. |
| Relational database | PostgreSQL 16. The `vector` extension is enabled by migration, but active embeddings are stored as JSONB rather than a PostgreSQL vector column. |
| Production vector store | Pinecone, configured for 1,024-dimensional dot-product vectors and immutable release namespaces. |
| Development vector store | JSON artifacts below `storage/ingestion`; local retrieval loads them into memory. |
| Job execution | CLI; FastAPI `BackgroundTasks` when Celery is disabled; Redis/Celery when enabled. |
| Document sources | Curated PDFs declared in `dataset/metadata.json`, plus administrator uploads recorded in a local upload manifest and Supabase Storage. |
| PDF extraction | PyMuPDF (`fitz`) text extraction. OCRmyPDF with Tesseract Indonesian and English is the conditional OCR path. |
| Chunking | Custom structure-aware, whitespace-window chunker. Defaults: target 350, maximum 550, overlap 60, minimum merge 180, parent context 1,200. |
| Embeddings | Production candidate: pinned `BAAI/bge-m3` via FlagEmbedding for dense and native sparse output. Sentence Transformers is the dense fallback. Deterministic hash embeddings support development/tests. OpenAI embeddings are optional. |
| LLM | Ingestion itself does not call an LLM or use prompts. Answer generation uses OpenRouter through the OpenAI SDK; this is downstream of ingestion. |
| RAG framework | Custom implementation; no LangChain, LlamaIndex, or Haystack dependency in the active path. |
| Logging/telemetry | Standard Python logging, per-build JSON logs, artifact manifests, and application-level Prometheus/OpenTelemetry support. Ingestion has limited stage-specific metrics. |

## Current ingestion pipeline

```text
CURATED PDF + dataset/metadata.json
          or
ADMIN UPLOAD + storage/ingestion/uploads/manifest.json
  ↓
DocumentMetadata resolution
  metadata.load_manifest / uploads.load_uploads_manifest / metadata.find_document
  ↓
File validation
  file_validation.validate_pdf_file
  ↓
Immutable build identity and raw PDF artifact
  builds.make_build_identity / pipeline.document_version_from_checksum
  artifacts.ArtifactStore.copy_raw_pdf
  ↓
Page extraction and quality assessment
  pdf_extractor.extract_pages / assess_text_quality
  ↓
Conditional whole-document OCR
  pdf_extractor.run_ocr → OCRmyPDF/Tesseract ind+eng → extract_pages
  ↓
Repeated margin cleaning
  pdf_extractor.remove_repeated_margin_noise
  ↓
Indonesian legal segmentation
  legal_parser.parse_legal_segments
  ↓
Structure-aware chunking
  chunker.build_chunks / split_legal_text_by_tokens / _coalesce_short_segments
  ↓
Dense+sparse embedding and JSONL checkpoints
  pipeline._embed_chunks_with_checkpoint / embeddings.embed_hybrid
  ↓
Quality report and immutable artifacts
  quality.build_quality_report / artifacts.ArtifactStore
  ↓
Optional PostgreSQL persistence
  database.persist_ingestion_result
  ↓
Human source verification, legal review, build approval, and publication
  routes_admin.verify_document_version / review_ingestion_build / update_publication
  ↓
Immutable Pinecone release namespace
  release_builder.build_index_release / PineconeRetrievalStore.upsert_document
  ↓
Evaluation and explicit release activation
  routes_admin transition endpoints / retrieval governance
```

### Where ingestion begins

| Mode | Entrypoint | Execution path |
| --- | --- | --- |
| CLI | `app.services.ingestion.cli.main` | Loads settings and metadata, constructs the embedding provider/build configuration, then calls `pipeline.ingest_document`. The CLI wraps the whole operation with transient retry logic. |
| API | `app.api.routes_ingestion.create_ingestion_job` | Creates or reuses document/version/build/job rows, then dispatches to Celery or FastAPI `BackgroundTasks`. |
| Celery | `app.services.ingestion.tasks.run_ingestion_task` | Calls `routes_ingestion._run_ingestion_background`, with late acknowledgement and up to three automatic retries. |
| In-process background | `routes_ingestion._run_ingestion_background` | Acquires a PostgreSQL advisory lock, marks rows running, and calls `pipeline.ingest_document`. |
| Manual governance/release | Admin routes in `routes_admin.py` | Verification, legal review, build approval, publication, release creation/build, evaluation, and activation remain explicit administrative steps. |

The ingestion orchestrator does **not** write directly to the active Pinecone namespace. Indexing is a separate release-building operation after governance checks.

## Important files and functions

| File | Important symbols | Responsibility |
| --- | --- | --- |
| `apps/api/app/services/ingestion/pipeline.py` | `ingest_document`, `document_version_from_checksum`, `_embed_chunks_with_checkpoint`, `_load_existing_result` | End-to-end document build orchestration, resume behavior, artifact creation, quality reporting, and optional persistence. |
| `apps/api/app/services/ingestion/file_validation.py` | `validate_pdf_file`, `compute_sha256`, `has_pdf_header` | Extension, magic-header, byte-size, checksum, and duplicate-checksum validation. |
| `apps/api/app/services/ingestion/pdf_extractor.py` | `extract_pages`, `assess_text_quality`, `remove_repeated_margin_noise`, `run_ocr` | PyMuPDF extraction, page scoring, margin cleaning, table counting, and OCRmyPDF execution. |
| `apps/api/app/services/ingestion/legal_parser.py` | `normalize_legal_line`, `parse_legal_segments` | Regex/state-machine detection of a subset of Indonesian legal hierarchy. |
| `apps/api/app/services/ingestion/chunker.py` | `build_chunks`, `split_legal_text_by_tokens`, `_coalesce_short_segments`, `build_retrieval_text` | Legal-boundary-aware merging, splitting, context prefixing, and chunk identity. |
| `apps/api/app/services/ingestion/embeddings.py` | `BGEM3EmbeddingProvider`, `HashEmbeddingProvider`, `OpenAIEmbeddingProvider`, `embed_hybrid` | Dense and sparse embedding providers. |
| `apps/api/app/services/ingestion/builds.py` | `IngestionBuildConfig`, `make_build_identity`, `runtime_provenance`, `validate_candidate_runtime` | Versioned pipeline configuration, fingerprints, and release-candidate preflight. |
| `apps/api/app/services/ingestion/quality.py` | `build_quality_report` | Page, chunk, structure, embedding, and provenance gates. |
| `apps/api/app/services/ingestion/artifacts.py` | `ArtifactStore` | Atomic JSON/raw PDF writes, JSONL checkpoints, and artifact locations. |
| `apps/api/app/services/ingestion/database.py` | `persist_ingestion_result` | Transactional persistence of document/version/build/chunk/embedding/job state. |
| `apps/api/app/services/ingestion/uploads.py` | `register_upload`, `build_upload_document`, `merge_documents` | Local upload storage/manifest and metadata inference. |
| `apps/api/app/api/routes_ingestion.py` | `create_ingestion_job`, `_run_ingestion_background` | API job lifecycle, advisory locking, dispatch, and failure status. |
| `apps/api/app/services/ingestion/tasks.py` | `run_ingestion_task`, `enqueue_ingestion`, `run_index_release_task` | Celery execution and retry configuration. |
| `apps/api/app/services/ingestion/release_builder.py` | `build_index_release`, `_version_is_eligible`, `_build_is_eligible`, `_validate_artifact_provenance` | Governance validation and immutable Pinecone release construction. |
| `apps/api/app/services/retrieval/pinecone_store.py` | `PineconeRetrievalStore.upsert_document`, `clear_namespace`, `_metadata_from_embedded_chunk` | Pinecone index creation, batched vector writes, namespace deletion, metadata mapping, and retrieval. |
| `apps/api/app/models/ingestion.py` | `Document`, `DocumentVersion`, `IngestionBuild`, `DocumentChunk`, `ChunkEmbedding`, `IngestionJob`, `RagIndexRelease` | Relational ingestion and release model. |
| `apps/api/app/core/config.py` | `Settings` | Providers, model revisions, dimensions, chunking, OCR, Pinecone, Redis, database, and environment policy. |

## Database tables involved

| Table | Role in ingestion |
| --- | --- |
| `documents` | Stable regulation identity and document-level metadata. |
| `document_versions` | Source checksum/size/path/URL, legal and verification state, publication state, current-version state, and artifact paths. |
| `ingestion_builds` | Immutable build/config/model provenance, quality report, review status, artifact manifest, and page dispositions. |
| `chunks` | Chunk text, legal path, page range, token count, retrieval text, checksum, and JSONB payload. |
| `chunk_embeddings` | Dense vector JSONB, sparse vector JSONB, model/revision/dimension/norm, and retrieval-text checksum. |
| `ingestion_jobs` | API/background job state, warnings, and artifact paths. |
| `document_relationships` | Amendment/replacement relationships used by retrieval and release snapshots. |
| `document_verification_audits` | Source/legal verification evidence and reviewer trail. |
| `rag_index_releases` | Immutable release namespace, selected versions/builds, model/prompt provenance, evaluation metrics, and lifecycle state. |

Migration `20260714_0001_ingestion_tables.py` enables the PostgreSQL `vector` extension, but `chunk_embeddings.embedding` is JSONB and no pgvector column or approximate-nearest-neighbor index is present. Pinecone is the production vector database.

## Detailed findings

### Document input

#### INP-01 — Malformed and protected PDFs are not explicitly classified — HIGH

**Current behavior:** `validate_pdf_file` checks file existence, a `.pdf` suffix, the `%PDF-` header, exact manifest size, and SHA-256. Structural parsing begins later in `pdf_extractor.extract_pages`. The active validator has no explicit encrypted/password-protected check and no typed malformed/corrupt/quarantine outcome.

**Problem:** A PDF can pass the header/checksum checks while being truncated, structurally corrupt, or encrypted. Failures then surface as generic extraction exceptions, and operators cannot distinguish a bad source from a transient runtime failure.

**Why this affects RAG quality:** A generic retry cannot repair a corrupt or protected source. Without a durable quarantine reason, a document may be repeatedly retried, manually waived without enough evidence, or confused with an OCR problem.

**Recommended solution:** Open the PDF during validation; inspect encryption/authentication, page count, cross-reference integrity, and ability to load every page. Introduce typed validation outcomes such as `malformed_pdf`, `password_required`, `zero_pages`, and `page_load_failure`, persist them on the build/job, and require source replacement or authorized password handling before ingestion.

**Affected files:** `file_validation.py`, `pdf_extractor.py`, `schemas.py`, `routes_ingestion.py`, `models/ingestion.py`, ingestion validation tests.

**Breaking-change risk:** Medium — job error schemas and status handling would gain typed failure states.

**Priority:** P1

#### INP-02 — Upload identity can collide by filename — HIGH

**Current behavior:** `routes_admin.upload_document` converts the sanitized filename stem to an uppercase hyphenated `document_id`. `register_upload` stores the source at `uploads/<document_id>/source.pdf` and replaces any manifest entry with the same ID. Supabase object identity includes a UUID, but the local ingestion identity does not.

**Problem:** Two different regulations with the same filename, or a replacement upload using the same filename, can overwrite the local source/manifest identity. There is no explicit create-new-version versus replace-document decision.

**Why this affects RAG quality:** The stable identity used for citations, relationships, governance, and version history can be silently reassigned to unrelated bytes or metadata.

**Recommended solution:** Generate document identity from normalized legal identity (`type`, `number`, `year`, issuer/jurisdiction) plus collision handling, not filename alone. Treat a matching legal identity with a new checksum as a new `DocumentVersion`; require an explicit administrative merge for ambiguous uploads.

**Affected files:** `routes_admin.py`, `uploads.py`, `metadata.py`, `models/ingestion.py`, upload/API tests.

**Breaking-change risk:** High — upload API responses, paths, foreign keys, and existing uploaded identities may require compatibility mapping.

**Priority:** P1

#### INP-03 — Duplicate bytes are warned about but not resolved — HIGH

**Current behavior:** `duplicate_ids_by_checksum` finds other document IDs with the same SHA-256. `ingest_document` records `duplicate_checksum_with=...` as a warning but continues to create chunks and embeddings.

**Problem:** There is no canonical duplicate, alias relationship, hard gate, or intentional-version rule. Identical PDFs can be indexed under several IDs.

**Why this affects RAG quality:** Duplicate vectors inflate a source's apparent support, crowd out diverse results, waste embedding/index capacity, and can produce several citations that are actually the same evidence.

**Recommended solution:** Add checksum uniqueness at the source-version layer with an explicit exception for documented aliases. Block accidental duplicate ingestion; record canonical/alias relationships; deduplicate retrieval by source checksum and legal identity during migration.

**Affected files:** `metadata.py`, `file_validation.py`, `pipeline.py`, `models/ingestion.py`, Alembic migrations, retrieval post-processing, duplicate tests.

**Breaking-change risk:** Medium — existing duplicate records may need reconciliation.

**Priority:** P1

#### INP-04 — Build identity can reuse stale legal metadata and code behavior — CRITICAL

**Current behavior:** `make_build_identity` hashes `document_id`, source SHA-256, and `IngestionBuildConfig.config_hash`. The config contains manually maintained pipeline/parser/chunker version strings and runtime package versions, but it does not hash `DocumentMetadata` or the source code. The API accepts `force`, resets the existing deterministic job/build, and the worker always invokes `ingest_document(..., resume=True)`. `_load_existing_result` can therefore return an existing build without reprocessing.

**Problem:** Changes to title, topics, legal status, source URL, verification metadata, issuer, or parser/chunker implementation can reuse artifacts produced with old metadata or code. `force=true` does not guarantee recomputation when the build fingerprint is unchanged.

**Why this affects RAG quality:** Stale legal status, titles, topics, retrieval prefixes, and source URLs can be published with apparently valid provenance. This can silently change which law is presented as current and where a user is sent to verify it.

**Recommended solution:** Include a canonical metadata hash and immutable code/build revision in the build fingerprint. Make forced ingestion generate a new attempt/build or pass `resume=False` after explicit confirmation. Store both content identity and processing-attempt identity, and reject release artifacts whose metadata snapshot does not match the selected document version.

**Affected files:** `builds.py`, `pipeline.py`, `routes_ingestion.py`, `database.py`, `release_builder.py`, `models/ingestion.py`, migrations, idempotency/re-ingestion tests.

**Breaking-change risk:** High — build IDs, job IDs, artifact paths, and release references change.

**Priority:** P0

#### INP-05 — Input support and limits are inconsistent — LOW

**Current behavior:** Only PDF is supported. Administrator uploads have a streamed 50 MB limit and PDF-header check. Curated inputs are limited indirectly by the exact size recorded in the manifest, with no general page or resource ceiling.

**Problem:** PDF-only support is reasonable for the current corpus, but curated and uploaded documents have different resource controls. Very large or pathological curated PDFs can consume unbounded extraction/OCR time and disk space.

**Why this affects RAG quality:** Resource exhaustion can delay the corpus and create partial artifacts, although it does not directly alter successfully extracted text.

**Recommended solution:** Keep PDF as the explicitly supported format, document it, and apply configurable byte/page/time limits consistently to every source. Reject unsupported formats with a typed reason rather than attempting implicit conversion.

**Affected files:** `file_validation.py`, `routes_admin.py`, `core/config.py`, ingestion documentation and tests.

**Breaking-change risk:** Low

**Priority:** P3

### PDF parsing

#### PDF-01 — Reading order and table contents are not preserved — HIGH

**Current behavior:** `extract_pages` uses `page.get_text("text")`. `page.find_tables()` contributes only a table count. The active path has no column reconstruction and does not serialize table cells or geometry. The unwired `app.services.rag.extraction` package contains stronger column/table utilities but is not called by production entrypoints.

**Problem:** PyMuPDF's plain-text order can interleave columns, detach headings, and flatten tables. Counting tables flags risk but does not retain their legal content.

**Why this affects RAG quality:** Indonesian regulations commonly place schedules, rates, definitions, and annex data in tables. Interleaved columns or flattened cells can reverse conditions, associate values with the wrong labels, or omit evidence entirely.

**Recommended solution:** Add layout-aware block extraction with bounding boxes and reading-order reconstruction; detect columns per page; serialize tables to a stable row/column representation while retaining page and bounding-box provenance. Route low-confidence layouts to review.

**Affected files:** `pdf_extractor.py`, `schemas.py`, `pipeline.py`, `quality.py`; potentially selected, integrated code from `app/services/rag/extraction/*`; parser fixtures for column/table PDFs.

**Breaking-change risk:** High — extracted text, chunk IDs, offsets, and embeddings will change.

**Priority:** P1

#### PDF-02 — OCR fallback is coarse and fails open — HIGH

**Current behavior:** Pages receive a quality score and `requires_ocr`. If any page requires OCR, `run_ocr` processes the whole document using OCRmyPDF with Indonesian and English, deskew/rotation, two jobs, and skip-text behavior unless missing spaces triggers forced OCR. After OCR, every page is re-extracted. OCR exceptions become warnings and ingestion continues with the original pages.

**Problem:** The retry unit is the whole PDF, OCR provenance is not page-specific, good born-digital text can be altered by whole-document OCR, and a failed OCR attempt does not automatically quarantine unresolved pages.

**Why this affects RAG quality:** OCR errors in article numbers, negation, monetary values, dates, or paragraph markers are high-impact legal errors. Continuing after failed OCR can publish incomplete content while only exposing a warning in build metadata.

**Recommended solution:** OCR only pages that need it where technically possible; retain original and OCR text per page; compare quality before/after; persist OCR engine/language/confidence for every page; make unresolved substantive pages a blocking gate unless explicitly dispositioned by a reviewer.

**Affected files:** `pdf_extractor.py`, `pipeline.py`, `schemas.py`, `quality.py`, `models/ingestion.py`, OCR fixtures and integration tests.

**Breaking-change risk:** Medium

**Priority:** P1

#### PDF-03 — Page boundaries survive extraction but not exact chunk attribution — HIGH

**Current behavior:** `ExtractedPage` preserves a 1-based page number. `LegalSegment` records `page_start` and `page_end`. All chunks created from a segment inherit the same range, even when character slices correspond to only one page or cross a specific page boundary.

**Problem:** Character offsets are relative to concatenated segment text and there is no span map from chunk characters back to source-page characters or PDF coordinates.

**Why this affects RAG quality:** A citation may list a broad page range or the wrong page for the quoted clause. Reviewers cannot reconstruct exactly which source glyphs produced a chunk.

**Recommended solution:** Carry page-span mappings through normalization, segmentation, coalescing, and splitting. Store per-chunk source spans containing page number, source character range, and optionally bounding boxes. Generate citations from those spans rather than inherited segment ranges.

**Affected files:** `schemas.py`, `pdf_extractor.py`, `legal_parser.py`, `chunker.py`, `database.py`, `pinecone_store.py`, citation tests.

**Breaking-change risk:** High — chunk schema and citation behavior change.

**Priority:** P1

#### PDF-04 — Corrupted characters are detected more than repaired — MEDIUM

**Current behavior:** `assess_text_quality` considers replacement glyphs, readability, alphanumeric ratio, and word spacing. `normalize_text` collapses whitespace by line. The active path does not apply comprehensive Unicode normalization or a controlled OCR-confusion repair policy.

**Problem:** Visually equivalent Unicode sequences, ligatures, non-breaking spaces, soft hyphens, and OCR confusions can survive into structure detection and embeddings.

**Why this affects RAG quality:** `Pasal`, article numbers, legal abbreviations, names, and search terms may fail exact matching or be embedded inconsistently.

**Recommended solution:** Add auditable Unicode normalization (normally NFC, with carefully tested compatibility normalization where appropriate), remove unsafe control characters, normalize spaces/dashes, and record every non-trivial repair. Do not silently autocorrect legal numbers without high-confidence rules and review flags.

**Affected files:** `pdf_extractor.py`, `legal_parser.py`, `quality.py`; optionally integrated `app/services/rag/extraction/normalize.py`; normalization tests.

**Breaking-change risk:** Medium

**Priority:** P2

### Text cleaning

#### CLN-01 — Cleaning does not repair common PDF line artifacts — MEDIUM

**Current behavior:** Text is normalized line by line and repeated margin lines are removed. There is no general dehyphenation, paragraph reflow, duplicate-block removal, soft-hyphen policy, or boilerplate classifier.

**Problem:** Words split across line endings remain split; paragraph sentences can remain fragmented; duplicated extraction blocks and legal-site boilerplate outside the page margins can survive.

**Why this affects RAG quality:** Fragmented terms weaken lexical and semantic retrieval, while duplicated/boilerplate text wastes tokens and can dominate similarity ranking.

**Recommended solution:** Implement a staged cleaner with reversible transformations and per-transformation counters. Use Indonesian-aware dehyphenation, conservative line reflow, normalized whitespace, exact/near-duplicate block detection, and configurable boilerplate patterns. Preserve the original page text alongside cleaned text.

**Affected files:** `pdf_extractor.py`, `pipeline.py`, `schemas.py`, `quality.py`, cleaner unit/regression fixtures.

**Breaking-change risk:** Medium

**Priority:** P2

#### CLN-02 — Header/footer removal is heuristic and not fully auditable — MEDIUM

**Current behavior:** `remove_repeated_margin_noise` examines the top and bottom three lines, removes recurrent signatures using a percentage/minimum threshold, recognizes several known BPK/JDIH/page-number patterns, and attempts to protect legal headings. Removed lines are stored per page.

**Problem:** Short documents may not meet recurrence thresholds, legitimate repeated provisions may look like margins, and variable headers/footers can evade signature matching.

**Why this affects RAG quality:** Retained headers create repetitive high-frequency chunks; removed legal headings erase structure and retrieval context.

**Recommended solution:** Combine recurrence with page coordinates, font/style signals, neighboring-page evidence, and allowlisted legal markers. Report removed text with page/coordinates and add corpus regression fixtures for BPK, JDIH, scanned, and annex layouts.

**Affected files:** `pdf_extractor.py`, `quality.py`, extraction/cleaning tests.

**Breaking-change risk:** Medium

**Priority:** P2

### Indonesian legal structure

#### LEG-01 — The active parser recognizes only part of the legal taxonomy — HIGH

**Current behavior:** `parse_legal_segments` recognizes `BAB`, `Bagian`, `Paragraf`, `Pasal`, numeric `Ayat`, letter points under an Ayat, `PENJELASAN`, and `LAMPIRAN`. It transitions from preamble to substantive text at the first Pasal. `Menimbang`, `Mengingat`, `Memutuskan`, named `Ketentuan Umum`, `Ketentuan Peralihan`, and `Ketentuan Penutup` are not explicit node types.

**Problem:** Important legal regions are retained only as undifferentiated text or chapter titles. Attachment and explanation substructures are shallow, and marker variants beyond the regex aliases can be missed.

**Why this affects RAG quality:** Queries about legal basis, transitional rules, definitions, enactment, and official explanations cannot be filtered or ranked by legal role. A definition and an explanatory note can be retrieved as if they had the same normative force.

**Recommended solution:** Define an explicit Indonesian regulation AST: document → opening/preamble (`Menimbang`, `Mengingat`, decision) → BAB → Bagian → Paragraf → Pasal → Ayat → Huruf/Angka, plus explanation and attachment trees. Preserve marker text, normalized identity, title, normative role, and nesting confidence.

**Affected files:** `legal_parser.py`, `schemas.py`, `chunker.py`, `database.py`, `pinecone_store.py`, parser fixtures across UU/PP/Permenaker formats.

**Breaking-change risk:** High — segment/chunk schemas and identifiers will change.

**Priority:** P1

#### LEG-02 — Hierarchy is flattened and partial parser misses are not surfaced — HIGH

**Current behavior:** Bagian and Paragraf are concatenated into one `section` string; `paragraph` represents Ayat and optional Huruf. Parser state continues across pages. A page-level unstructured fallback occurs only when the entire document yields no segments.

**Problem:** The model cannot independently represent Bagian, Paragraf, Ayat, Huruf, or Angka. If only some markers are missed, their text can be attached to the current state without a localized parse warning.

**Why this affects RAG quality:** Filters and citations cannot reconstruct the exact hierarchy, and a missed boundary can contaminate many later chunks by carrying stale parser state.

**Recommended solution:** Use distinct hierarchy fields and stable node IDs. Validate marker ordering, article/paragraph sequences, nesting legality, and state resets. Emit per-page/per-marker parse issues and confidence; fall back locally rather than only at document level.

**Affected files:** `legal_parser.py`, `schemas.py`, `quality.py`, `models/ingestion.py`, migrations, metadata and parser tests.

**Breaking-change risk:** High

**Priority:** P1

### Chunking

#### CHK-01 — Token limits are internally inconsistent — HIGH

**Current behavior:** Standard chunking uses whitespace spans with target 350, maximum 550, and overlap 60. Stored `token_count` uses a different regex that counts punctuation separately. The quality gate accepts up to `max_chunk_tokens * 3`. Current artifacts include maxima above 550, including 1,075 and 1,106 tokens, while still reporting a passed quality status.

**Problem:** The configured maximum is not an enforced embedding/generation token limit and the metric does not measure the same units used by splitting or the BGE tokenizer.

**Why this affects RAG quality:** Overlong chunks dilute relevance, can be truncated by the embedding model's 550-token passage limit, hide operative clauses near the end, and make retrieval evaluation misleading.

**Recommended solution:** Tokenize with the pinned embedding tokenizer before splitting and quality checks. Treat the configured maximum as a hard limit after adding retrieval prefixes; separately report body and final retrieval-text tokens. Remove the `* 3` tolerance or rename it as an explicit emergency ceiling that blocks release.

**Affected files:** `chunker.py`, `quality.py`, `embeddings.py`, `builds.py`, chunker/quality regression tests.

**Breaking-change risk:** High — chunk boundaries, IDs, embeddings, and artifact checksums change.

**Priority:** P1

#### CHK-02 — Oversized legal units lose precise parent and source relationships — HIGH

**Current behavior:** Short segments can be merged within matching article/chapter/section/type boundaries. Oversized segment text is split by whitespace and punctuation with overlap. Each child repeats up to 1,200 whitespace tokens of `parent_text`, but there is no persisted parent node/vector ID. Splits inherit the segment's whole page range.

**Problem:** A large Pasal or Ayat can be split mid-condition, while its children have neither exact source spans nor a stable parent-child graph. When differing paragraph segments are coalesced, `paragraph` becomes `None`.

**Why this affects RAG quality:** Exceptions, provisos, and definitions can be separated from the rule they qualify. Context expansion cannot deterministically fetch the authoritative parent or adjacent legal node.

**Recommended solution:** Persist legal nodes and parent IDs separately from retrieval children. Prefer boundaries at Ayat/Huruf/Angka and sentences; split inside a legal leaf only as a last resort. Store ordered child indexes, exact source spans, sibling links, and parent summaries/text without duplicating the full parent in every vector.

**Affected files:** `chunker.py`, `schemas.py`, `models/ingestion.py`, `database.py`, `pinecone_store.py`, retrieval context expansion, migrations and tests.

**Breaking-change risk:** High

**Priority:** P1

#### CHK-03 — Chunking is structure-aware but not semantic or distribution-calibrated — MEDIUM

**Current behavior:** The active algorithm is custom and deterministic. It is token-like and section-aware, not recursive-character by default, semantic, or a complete parent-child strategy. A character-based path exists only when `max_chars` is explicitly supplied. Overlap is fixed at 60 whitespace tokens.

**Problem:** Fixed target and overlap values are not justified by corpus distributions or retrieval evaluation. Very short provisions may be merged, while long coherent clauses may be cut based on punctuation availability.

**Why this affects RAG quality:** Too much overlap creates near-duplicate results; too little loses cross-boundary conditions. Fixed sizes can underperform across short Pasal, long explanations, and tabular attachments.

**Recommended solution:** Keep legal boundaries primary, then calibrate leaf splitting and overlap using corpus token percentiles and retrieval ablations. Measure duplicate-result rate, context recall, citation accuracy, and answer faithfulness for candidate configurations before changing defaults.

**Affected files:** `chunker.py`, `builds.py`, `quality.py`, evaluation runner/dataset, chunk regression tests.

**Breaking-change risk:** Medium

**Priority:** P2

### Metadata and provenance

#### MET-01 — Chunk metadata cannot fully reconstruct the legal source hierarchy — HIGH

**Current behavior:** `Chunk` carries document ID, chapter, combined section, article, paragraph, page range, topics, legal status, source URL, build ID, offsets, type, retrieval text, parent text, and checksum. Regulation type/number/year/title and document version are available through document/version records and Pinecone metadata, but are not first-class fields on the chunk dataclass; version is encoded in the chunk ID. Bagian/Paragraf/Ayat are not independent fields.

**Problem:** A standalone chunk artifact cannot unambiguously reconstruct all requested provenance. Joined data can reconstruct document metadata, but not the missing hierarchy or exact source spans.

**Why this affects RAG quality:** Retrieval filters, citation formatting, audits, and offline evaluation become dependent on fragile ID parsing and joins. Legal references can be incomplete or overly broad.

**Recommended solution:** Define a versioned provenance schema containing document/version/build IDs, regulation identity, title, source checksum/URL, distinct legal hierarchy IDs/titles, exact page spans, normative role, and parent/sibling IDs. Validate required metadata on every chunk before embedding.

**Affected files:** `schemas.py`, `chunker.py`, `database.py`, `models/ingestion.py`, `pinecone_store.py`, migrations and metadata tests.

**Breaking-change risk:** High

**Priority:** P1

#### MET-02 — Pinecone omits some artifact-integrity fields — MEDIUM

**Current behavior:** `_metadata_from_embedded_chunk` stores extensive document, version, legal path, page, model, build, text, parent, and offset metadata. It does not currently include the source SHA-256, chunk `artifact_checksum`, retrieval-text SHA-256, or `chunk_type`. Long text fields are truncated to the Pinecone metadata limit.

**Problem:** A retrieved vector cannot be independently reconciled with the immutable artifact manifest using only its Pinecone metadata.

**Why this affects RAG quality:** Index drift or stale vector payloads are harder to detect during incident response and release verification.

**Recommended solution:** Add compact source/chunk/retrieval checksums, schema version, and chunk type to vector metadata. Keep full text in the canonical artifact/database and verify truncated Pinecone text against checksums rather than treating it as authoritative.

**Affected files:** `pinecone_store.py`, `release_builder.py`, retrieval schemas and Pinecone tests.

**Breaking-change risk:** Low

**Priority:** P2

### Embedding

#### EMB-01 — Provider failures lack bounded, observable batch recovery — HIGH

**Current behavior:** Embeddings are processed in batches (default 16). A completed batch is appended and fsynced to a JSONL checkpoint. Cache reuse verifies chunk ID, model, revision, and retrieval-text checksum. The providers do not define explicit timeout, rate-limit, or provider-specific retry behavior. CLI retries wrap the whole ingestion operation; Celery retries every exception up to three times.

**Problem:** A persistent invalid request and a transient provider limit receive similar task-level retry treatment. Batch failure details, attempt count, latency, and failed chunk IDs are not durably recorded. OpenAI client defaults govern timeouts implicitly.

**Why this affects RAG quality:** Repeated retries can waste cost and time, while partial failure diagnosis is difficult. If operator workarounds bypass gates, missing embeddings create corpus holes.

**Recommended solution:** Add provider-specific timeout/retry policies with exponential backoff and `Retry-After` support; classify retryable versus permanent failures; persist batch attempt/failure records and chunk IDs; reconcile embedded count/checksums before completion. Keep checkpoint writes atomic per successful batch.

**Affected files:** `embeddings.py`, `pipeline.py`, `retry.py`, `tasks.py`, `models/ingestion.py`, provider and failure-injection tests.

**Breaking-change risk:** Medium

**Priority:** P1

#### EMB-02 — Model tracking is good, but cost and execution telemetry are incomplete — MEDIUM

**Current behavior:** Build and embedding rows track model, revision, dimensions, norm, batch size, and retrieval-text checksum. Release-candidate configuration requires pinned BGE-M3, 1,024 dimensions, native sparse output, and required local runtime commands. No per-batch token/input count, wall time, memory/accelerator information, provider request ID, or cost estimate is recorded.

**Problem:** Reproducibility captures software versions but not enough execution characteristics to compare throughput, failures, or hosted-provider spending.

**Why this affects RAG quality:** Teams cannot reliably correlate degraded vector quality with truncation, resource pressure, or provider changes, and cannot forecast re-ingestion cost.

**Recommended solution:** Persist embedding batch metrics: input token count under the actual tokenizer, latency, attempts, device, peak memory where available, provider request IDs, and estimated/actual cost for hosted models. Aggregate these in the quality report and job UI.

**Affected files:** `embeddings.py`, `pipeline.py`, `quality.py`, `models/ingestion.py`, admin job payloads.

**Breaking-change risk:** Low

**Priority:** P2

### Indexing and release management

#### IDX-01 — Pinecone release writes are not reconciled after upsert — HIGH

**Current behavior:** `build_index_release` verifies governance and artifact provenance, clears the immutable namespace, then sequentially calls `upsert_document`. `upsert_document` batches 100 vectors and totals the response's `upserted_count`, falling back to batch length when it is absent. On failure, the release is marked failed; a retry clears and rebuilds the namespace.

**Problem:** There is no post-write count/read-back/checksum verification. A failed attempt can leave a partial inactive namespace until retry or manual cleanup, and the response fallback can report success without server confirmation.

**Why this affects RAG quality:** Activating an incompletely built namespace would create silent retrieval gaps. Even when activation is correctly blocked, untracked partial namespaces consume resources and complicate operations.

**Recommended solution:** Build into a uniquely named staging namespace, verify vector count and a deterministic sample/all-ID manifest, compare metadata checksums, then mark the release build successful. Delete failed staging namespaces according to a retention policy. Never infer an upsert count when the provider does not confirm it.

**Affected files:** `release_builder.py`, `pinecone_store.py`, `models/ingestion.py`, release integration tests.

**Breaking-change risk:** Medium

**Priority:** P1

#### IDX-02 — End-to-end ingestion is not transactional — HIGH

**Current behavior:** `persist_ingestion_result` deletes and replaces chunks/embeddings for one build in a single PostgreSQL transaction. Artifact writes use temporary files, fsync, and replacement; embedding checkpoints are append-only. Pinecone is written later in another process. These boundaries cannot participate in one transaction.

**Problem:** Failure between source copy, artifact creation, database commit, and external indexing can leave a mixture of valid checkpoints, unpersisted artifacts, failed job records, or partial vector namespaces.

**Why this affects RAG quality:** Operators may mistake the presence of artifacts or a completed stage for a fully indexed document. Manual recovery can select inconsistent build components.

**Recommended solution:** Model ingestion as a persisted state machine with explicit stage checkpoints and reconciliation. Make each stage idempotent, promote artifacts only after checksum verification, commit a completed-build manifest last, and allow release indexing only from that manifest. Add cleanup/recovery commands for abandoned attempts.

**Affected files:** `pipeline.py`, `artifacts.py`, `database.py`, `routes_ingestion.py`, `tasks.py`, `release_builder.py`, models/migrations.

**Breaking-change risk:** High

**Priority:** P1

#### IDX-03 — pgvector is enabled but not used — LOW

**Current behavior:** The first ingestion migration creates the PostgreSQL `vector` extension, but dense embeddings are JSONB and no vector index exists. Pinecone is the production vector store; JSON artifacts support local retrieval.

**Problem:** The database schema suggests a pgvector capability that does not exist, and JSONB vectors are large and unsuitable for similarity search.

**Why this affects RAG quality:** This is primarily an operational/documentation ambiguity. It becomes a quality risk only if an operator assumes PostgreSQL retrieval is equivalent to Pinecone.

**Recommended solution:** Explicitly document Pinecone as the only production vector index. Either remove the unused extension in a later migration or implement a deliberately supported pgvector backend with a vector column, dimension constraint, and ANN index; do not leave an implied hybrid state.

**Affected files:** `20260714_0001_ingestion_tables.py`, future Alembic migration, `models/ingestion.py`, architecture/deployment documentation.

**Breaking-change risk:** Low if documentation-only; Medium if schema is changed.

**Priority:** P3

### Reliability and observability

#### REL-01 — In-process background ingestion is not durable and failure records are coarse — HIGH

**Current behavior:** When Celery is disabled, API ingestion uses FastAPI `BackgroundTasks`. Production Celery uses late acknowledgements, reject-on-worker-loss, exponential retry/jitter, and three retries. `_run_ingestion_background` stores only `ingestion_failed:<ExceptionType>` in job warnings, while detailed stack traces stay in process logs.

**Problem:** In-process jobs are lost on restart. Generic exception-type records omit stage, source page, batch, retryability, and operator guidance. Celery retries all exception types.

**Why this affects RAG quality:** Documents can remain queued/running or repeatedly fail without a recoverable diagnosis, delaying updates to current regulations and encouraging unsafe manual intervention.

**Recommended solution:** Require a durable queue outside explicit local development. Persist structured failure events with stage, error code, retryability, attempt, page/chunk/batch identifiers, and redacted message. Add stale-running job recovery and dead-letter/quarantine workflows.

**Affected files:** `routes_ingestion.py`, `tasks.py`, `models/ingestion.py`, `core/config.py`, job API tests and operations documentation.

**Breaking-change risk:** Medium

**Priority:** P1

#### REL-02 — Stage-level observability and reproducibility are incomplete — MEDIUM

**Current behavior:** The pipeline writes a JSON result log with total elapsed seconds, standard logging reports job transitions, build configuration captures package/command versions, and artifact manifests capture hashes and sizes. There are no ingestion-specific counters/histograms per stage, and the code revision is not recorded.

**Problem:** It is difficult to identify whether validation, extraction, OCR, parsing, embedding, persistence, or indexing caused a throughput or quality regression. Manually incremented version strings can drift from actual code.

**Why this affects RAG quality:** Slow or degraded stages may remain undetected across a corpus refresh, and a supposedly reproducible build cannot identify the exact implementation that produced it.

**Recommended solution:** Emit structured logs and metrics keyed by document/version/build/job and stage. Record durations, counts, warnings, retries, resource use, and a source-code/container image revision in the immutable manifest. Alert on failed/review-required rates and anomalous distributions.

**Affected files:** `pipeline.py`, `routes_ingestion.py`, `tasks.py`, `release_builder.py`, `builds.py`, application telemetry configuration.

**Breaking-change risk:** Low

**Priority:** P2

#### REL-03 — Local artifact retrieval can silently produce invalid similarity scores — HIGH

**Current behavior:** Current stored hash artifacts use 1,024 dimensions. `RetrievalEngine` constructs `HashEmbeddingProvider()` with its default 64 dimensions. `cosine_similarity` returns zero for incompatible lengths, and `normalize_scores` maps a uniform score set to `1.0`.

**Problem:** Local retrieval can turn a dimension mismatch into uniformly perfect normalized semantic scores instead of failing closed.

**Why this affects RAG quality:** Development diagnostics and evaluations may rank unrelated chunks as if semantic similarity succeeded, masking ingestion or model-configuration defects before release.

**Recommended solution:** Instantiate query embeddings from the active artifact/release manifest, validate model/revision/dimension before retrieval, and raise a typed index-space mismatch. For uniform zero scores, preserve zero or mark semantic scoring unavailable rather than normalizing to one.

**Affected files:** `retrieval/engine.py`, `retrieval/scoring.py`, `retrieval/store.py`, `rag/retrieval/consistency.py`, retrieval consistency tests.

**Breaking-change risk:** Medium

**Priority:** P1

#### REL-04 — Parallel unwired RAG modules create architecture drift — MEDIUM

**Current behavior:** `app.services.rag.*` implements additional collection, encrypted-file handling, extraction, normalization, table handling, structure, metadata, chunking, embedding, indexing guards, and validation. Active entrypoints import `app.services.ingestion.*`. `app.services.rag.retrieval.consistency` currently self-imports and fails collection.

**Problem:** Two implementations can evolve independently, and tests for the newer modules may be mistaken for coverage of production behavior.

**Why this affects RAG quality:** Fixes to table extraction, normalization, or validation can appear complete while never affecting ingested vectors. Divergent schemas also increase migration risk.

**Recommended solution:** Declare one authoritative pipeline contract. Before integrating anything, map each unwired capability to a verified production gap, select components deliberately, and add entrypoint-level wiring tests. Remove or archive superseded modules only after migration and artifact compatibility are proven.

**Affected files:** `app/services/rag/*`, `app/services/ingestion/*`, application entrypoints, RAG and ingestion tests.

**Breaking-change risk:** High if pipelines are consolidated; None for documenting ownership.

**Priority:** P2

### Testing

#### TST-01 — The complete backend suite does not currently collect or run cleanly — HIGH

**Current behavior:** The focused ingestion/RAG component selection passes 120 tests. The complete suite fails collection because `test_proxy_trust.py` imports missing `app.main.state` and `rag/retrieval/consistency.py` imports itself. Excluding those files yielded 353 passes and 44 errors, predominantly because the required test PostgreSQL database was unavailable.

**Problem:** CI-equivalent confidence cannot be obtained from one command in the audited environment. Collection failures hide later failures, while infrastructure-dependent tests do not distinguish unavailable prerequisites from behavior regressions.

**Why this affects RAG quality:** Broken release gates can allow parser, metadata, governance, or retrieval regressions to reach production despite a healthy focused suite.

**Recommended solution:** Fix collection independently of feature work, provision/migrate PostgreSQL deterministically in CI, separate unit and integration markers, and make prerequisite failures explicit. Require both active-pipeline tests and entrypoint-level integration tests for ingestion releases.

**Affected files:** `tests/test_proxy_trust.py`, `app/main.py`, `rag/retrieval/consistency.py`, `tests/conftest.py`, CI/test documentation.

**Breaking-change risk:** Low

**Priority:** P1

#### TST-02 — No test proves a real production ingestion and release flow — HIGH

**Current behavior:** Unit tests cover validation, parser/chunker behavior, quality reports, hash embeddings, retries, routes, governance, and fake Pinecone/provider interactions. The repository has PDF data and local artifacts, but inspected artifacts use hash embeddings. There is no demonstrated automated run of representative born-digital, two-column, table-heavy, scanned, malformed, and encrypted PDFs through OCR, pinned BGE-M3, PostgreSQL, Pinecone staging, verification, and activation.

**Problem:** Mocked components verify contracts but not model downloads, native dependencies, real PDF layouts, provider limits, index consistency, or end-to-end provenance.

**Why this affects RAG quality:** Integration failures and extraction degradation are most likely at component boundaries that unit tests replace with fakes.

**Recommended solution:** Create a small legally safe fixture corpus covering each layout/failure class. Run deterministic extraction/chunk metadata golden tests on every change, BGE-M3/PostgreSQL integration tests in CI, and a controlled Pinecone staging smoke test before release. Never place full sensitive or copyrighted documents in test snapshots.

**Affected files:** ingestion/RAG tests, test fixtures, CI configuration, `docs/TESTING.md`, release runbook.

**Breaking-change risk:** None

**Priority:** P1

### Ingestion-quality evaluation

#### EVA-01 — Quality reports do not measure extraction completeness end to end — HIGH

**Current behavior:** `build_quality_report` records page count, empty/OCR/unresolved pages, table count, removed margin lines, chunk/article counts, missing detected articles, heading/margin/duplicate chunk indicators, under-80/max token counts, embedding count/dimension/norm/sparse coverage, page-range validity, and source checksum/verification gates.

**Problem:** It does not measure expected versus extracted page coverage, characters/words before and after cleaning/OCR, per-page OCR improvement, parse errors/confidence, article/Ayat sequence gaps across the source, chunk percentiles/histograms, overlap ratio, orphan hierarchy nodes, missing required metadata, embedding attempts/failures/latency, or indexed-vector reconciliation. Table detection does not evaluate table fidelity.

**Why this affects RAG quality:** A build can pass while omitting clauses, flattening tables, producing oversized chunks, or losing hierarchy, because the report measures internal consistency more than fidelity to the source.

**Recommended solution:** Add a versioned ingestion evaluation report with source-page reconciliation, extraction delta metrics, legal-structure coverage/sequence checks, chunk distribution and duplication metrics, required-metadata coverage, embedding failure telemetry, and post-index count/checksum verification. Establish corpus-specific thresholds and reviewer dispositions.

**Affected files:** `quality.py`, `pipeline.py`, `release_builder.py`, `models/ingestion.py`, evaluation artifacts/UI and regression tests.

**Breaking-change risk:** Medium — build quality schemas and gates expand.

**Priority:** P1

#### EVA-02 — Advisory quality gates are treated as blocking at release time — HIGH

**Current behavior:** `quality.build_quality_report` labels unresolved pages, sparse completeness, margin noise, heading-only chunks, and duplicate retrieval text as non-blocking advisory gates when calculating `status`. `release_builder._build_is_eligible` subsequently requires `all(bool(value) for value in gates.values())`, making every advisory gate blocking for release.

**Problem:** Ingestion status and release eligibility implement different policies for the same gate set. A build can be `completed` yet be impossible to include in a release without a clear reason in the ingestion status.

**Why this affects RAG quality:** Operators cannot reliably interpret completion, automate release readiness, or distinguish a true legal-quality block from an accepted advisory condition. Workarounds may encourage manual state changes rather than evidence-based review.

**Recommended solution:** Give every gate a persisted severity/disposition (`blocking`, `advisory`, `waived-with-review`) and use one policy evaluator in ingestion, review, and release building. Record reviewer waivers with page/chunk evidence and never allow waivers for checksum, dimension, or missing-vector integrity failures.

**Affected files:** `quality.py`, `release_builder.py`, `routes_admin.py`, `models/ingestion.py`, migrations and governance/release tests.

**Breaking-change risk:** Medium

**Priority:** P1

## Requirement coverage matrix

Status definitions: **Supported** means active and directly evidenced; **Partial** means present but incomplete; **Absent** means no active implementation; **Unwired** means present only in `app.services.rag.*`; **Unverified** means configuration/code exists but no live external execution was established.

### Document input and identity

| Requirement | Status | Evidence/assessment |
| --- | --- | --- |
| File validation | Partial | Extension, magic header, exact size, and SHA-256 are checked; PDF structure/encryption is not. |
| Supported formats | Supported | PDF only, explicitly enforced. |
| Malformed/corrupt PDF handling | Partial | PyMuPDF exceptions fail the job, but there is no typed quarantine state. |
| Password-protected PDFs | Absent | No active encrypted/authentication preflight. Stronger checks exist only in unwired collection/loading code. |
| Duplicate documents | Partial | Duplicate SHA-256 IDs are warned about; ingestion continues. |
| Document identity | Partial | Curated manifest IDs are explicit; upload IDs derive from filenames and can collide. |
| Versioning | Partial | Content-derived integer version plus immutable builds; no legal/semantic version relationship. |
| Re-ingestion | Partial | Content/config changes create builds; forced identical ingestion resumes stale artifacts. |
| Idempotency | Partial | Deterministic IDs, locks, checkpoints, and DB replacement help; metadata/code changes are outside the identity. |

### PDF parsing and cleaning

| Requirement | Status | Evidence/assessment |
| --- | --- | --- |
| Extraction quality scoring | Supported | Per-page length/readability/alphanumeric/replacement/spacing checks. |
| Page preservation | Partial | Pages survive extraction; exact chunk-to-page spans do not. |
| Layout handling | Partial | Rotation and plain text exist; layout geometry is discarded. |
| Two-column PDFs | Absent | No active column reconstruction. Unwired extractor has related utilities. |
| Tables | Partial | Tables are counted, not preserved as structured content. |
| Scanned PDFs | Partial | OCR fallback exists and uses Indonesian/English. |
| OCR fallback | Partial | Whole-document fallback; can continue after failure. |
| Corrupted characters | Partial | Quality flags detect some corruption; repair/normalization is limited. |
| Unicode normalization | Partial | Whitespace normalization exists; comprehensive Unicode normalization is not active. |
| Headers/footers | Partial | Repeated margin heuristic plus known patterns. |
| Repeated page titles/page numbers | Partial | Some recurrence/pattern handling, not layout-aware. |
| Whitespace | Supported | Per-line whitespace collapse. |
| Line-break artifacts | Partial | Lines retained; no general paragraph reflow. |
| Hyphenation | Absent | No active dehyphenation. |
| Duplicated text | Partial | Duplicate final retrieval text is measured, not cleaned. |
| Boilerplate | Partial | Known margin patterns only. |

### Legal structure and chunking

| Requirement | Status | Evidence/assessment |
| --- | --- | --- |
| Pembukaan/preamble | Partial | Initial text uses a preamble segment type, without detailed nodes. |
| BAB | Supported | Roman numeral headings recognized. |
| Bagian | Partial | Recognized but flattened into `section`. |
| Paragraf | Partial | Recognized but flattened into `section`. |
| Pasal | Supported | Numeric Pasal with optional letter suffix recognized. |
| Ayat | Partial | Leading numeric parentheses recognized under a Pasal. |
| Huruf/Angka | Partial | Huruf under an Ayat is recognized; general nested numbering is incomplete. |
| Menimbang | Absent | Not an explicit active node type. |
| Mengingat | Absent | Not an explicit active node type. |
| Memutuskan | Absent | Not an explicit active node type. |
| Ketentuan Umum/Peralihan/Penutup | Partial | Can survive as BAB text/title, not semantic section types. |
| Penjelasan | Partial | Top-level type switch, shallow internal hierarchy. |
| Lampiran | Partial | Top-level type switch; table/layout structure remains weak. |
| Character chunking | Optional | Used only when `max_chars` is explicitly provided. |
| Token chunking | Partial | Whitespace-token splitting; stored counts use another heuristic. |
| Recursive chunking | Absent | No recursive splitter in active path. |
| Semantic chunking | Absent | No embedding/similarity-based boundary selection. |
| Section/structure-aware chunking | Supported | Coalescing respects article/chapter/section/type boundaries. |
| Parent-child chunking | Partial | Parent text is copied/truncated; no persistent parent graph. |
| Chunk size/overlap | Supported but weakly enforced | 350 target, 550 max, 60 overlap; artifacts exceed the stated maximum. |
| Token distribution measurement | Partial | Maximum and under-80 count only; no percentiles/histogram. |

### Metadata, embeddings, indexing, and reliability

| Requirement | Status | Evidence/assessment |
| --- | --- | --- |
| Document/type/number/year/title | Supported | Document registry and Pinecone metadata; not all first-class on `Chunk`. |
| BAB/Bagian/Paragraf/Pasal/Ayat | Partial | Chapter/article plus flattened section/paragraph. |
| Source page | Partial | Page range, not exact source spans. |
| Source URL | Supported | Manifest/version/chunk/Pinecone metadata. |
| Parent section | Partial | Parent text exists; stable parent node does not. |
| Document version | Supported | Version rows and Pinecone metadata; encoded rather than explicit on `Chunk`. |
| Embedding model/dimensions | Supported | BGE-M3, pinned revision, 1,024 dimensions for release candidates. |
| Embedding batching | Supported | Default batch size 16. |
| Embedding retries/timeouts/rate limits | Partial | Whole-job retries; no provider-specific policy/telemetry. |
| Failed embeddings | Partial | Failed batch stops build; no durable per-batch failure record. |
| Cost measurement | Absent | No hosted embedding cost accounting. |
| Embedding version tracking | Supported | Model/revision/dimension and text checksum persisted. |
| Vector storage | Supported | Pinecone production; JSON artifacts/JSONB persistence. |
| Vector indexing | Supported/Unverified | Pinecone index setup and batch upsert implemented; live service not exercised in this audit. |
| Uniqueness | Partial | Deterministic chunk IDs; no source-checksum uniqueness constraint. |
| Transactions | Partial | PostgreSQL build persistence is transactional; external stages are not. |
| Partial ingestion/rollback | Partial | Checkpoint/resume and release isolation; no unified rollback/reconciliation. |
| Stale vectors | Partial | Immutable active releases protect serving; partial inactive namespaces can remain. |
| Retries/checkpointing | Supported | CLI/Celery retry and embedding JSONL checkpoint. |
| Error handling | Partial | Exceptions fail jobs; persisted diagnostics are coarse. |
| Observability/logging | Partial | Logs/artifacts exist; stage metrics and structured durable errors are limited. |
| Reproducibility | Partial | Config/runtime hashes exist; metadata and code revision are missing. |

### Testing and ingestion evaluation

| Requirement | Status | Evidence/assessment |
| --- | --- | --- |
| Parser tests | Supported | Active and unwired parser tests exist. |
| Cleaner tests | Partial | Margin/normalization tests exist; active cleaner coverage is not corpus-complete. |
| Chunker tests | Supported | Boundary, sizing, and metadata behaviors covered at unit level. |
| Metadata tests | Supported | Manifest/citation and unwired metadata tests exist. |
| Integration tests | Partial | API/provider/Pinecone fakes exist; full live dependency path is unproven. |
| Ingestion regression tests | Partial | Component regressions exist; no representative golden PDF corpus end-to-end. |
| Page coverage | Partial | Unresolved-page heuristic, not source/extracted span coverage. |
| Extraction completeness | Absent | No expected character/word/content baseline. |
| Parsing errors | Partial | Quality flags/warnings, no structured parser error inventory. |
| Empty pages | Supported | Explicitly reported. |
| Chunk count | Supported | Explicitly reported. |
| Chunk length distribution | Partial | Maximum and short-count only. |
| Duplicate chunks | Supported | Exact retrieval-text hash duplicates reported. |
| Missing metadata | Partial | A few path gates, no required-field coverage matrix. |
| Legal structure coverage | Partial | Detected article coverage only. |
| Embedding failures | Partial | Count equality gate; no attempt/failure telemetry. |
| Indexing failures | Partial | Release status/error type, no vector reconciliation report. |

## Prioritized remediation roadmap

### P0 — Make build and version identity legally safe

1. Separate document identity, source-version identity, build identity, and ingestion-attempt identity.
2. Include canonical metadata and code/container revisions in build provenance.
3. Make forced ingestion actually rebuild, and prohibit releases whose metadata snapshot differs from the selected version.

### P1 — Establish source fidelity and release integrity

1. Add structural/encryption validation and durable quarantine states.
2. Preserve layout, tables, OCR provenance, and exact page/source spans.
3. Introduce a complete Indonesian legal hierarchy and stable parent-child nodes.
4. Enforce limits using the actual embedding tokenizer.
5. Resolve checksum duplicates and upload identity collisions.
6. Add provider-specific embedding failure handling and post-Pinecone reconciliation.
7. Unify quality-gate policy across ingestion, review, and release.
8. Restore one-command backend test collection and add a real production-path integration corpus.

### P2 — Improve cleaning, metadata, and operations

1. Add reversible Unicode normalization, dehyphenation, reflow, duplicate removal, and layout-aware margin cleaning.
2. Expand Pinecone integrity metadata and ingestion-stage metrics.
3. Calibrate chunk/overlap settings through retrieval and citation evaluation.
4. Declare ownership between `app.services.ingestion` and the unwired `app.services.rag` package before consolidation.

### P3 — Remove architectural ambiguity

1. Apply consistent resource limits to curated and uploaded PDFs.
2. Document or remove the unused pgvector extension unless a supported PostgreSQL vector backend is intentionally implemented.

## Questions and uncertainties found in the code

1. Is `app.services.rag.*` intended to replace `app.services.ingestion.*`, or is it an experimental library? No active entrypoint or migration boundary answers this.
2. Is `force=true` intended to rerun computation or only requeue/re-persist an immutable build? The API message says “mengulang,” but the worker always resumes.
3. Are advisory quality gates intended to permit release? `quality.py` says yes; `release_builder.py` requires every gate to pass.
4. Is `local-hash-embedding-v1` strictly a development artifact, or is artifact-mode retrieval expected to be a reliable local evaluation path? Current query/vector dimensions disagree.
5. What is the canonical identity policy when two official sites publish byte-identical files or when a regulation is republished with different scan bytes but identical legal effect?
6. How should corrigenda, amendments, consolidated texts, explanations, and attachments relate to the primary regulation version?
7. Which pages may be explicitly dispositioned as non-retrievable, and what reviewer evidence is required before an unresolved page can be released?
8. Is Pinecone namespace cleanup handled by infrastructure outside this repository? No in-repository retention or failed-namespace cleanup job was found.
9. Are current production Pinecone, PostgreSQL, Supabase, Redis/Celery, OCR, and BGE-M3 services deployed with the exact checked-in settings? This audit did not access live services.
10. Which official page/citation convention should users see when printed page numbers differ from PDF page indexes? The current model stores only numeric extraction pages.

## Production-readiness conclusion

The current implementation is a credible controlled ingestion system with strong beginnings in immutable artifacts and human-governed releases. It should be treated as **review-required and operator-supervised**, not as an unattended production legal ingestion service. The P0 build-identity issue must be resolved before metadata-only updates or forced re-ingestion can be trusted. The P1 source-fidelity, exact-provenance, index-reconciliation, and end-to-end test gaps should be closed before the system makes broad claims of complete and verifiable coverage of Indonesian employment regulations.
