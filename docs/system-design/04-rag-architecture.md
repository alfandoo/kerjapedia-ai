# 04 — RAG Architecture

```mermaid
sequenceDiagram
    participant U as User
    participant A as FastAPI
    participant Q as Query Understanding
    participant V as Upstash HYBRID
    participant G as Neon Governance
    participant R as Rerank+MMR
    participant C as Context Builder
    participant L as Groq
    participant VF as Verifier
    U->>A: Auth, rate-limit, validation
    A->>Q: intent, topic, pasal/ayat, regulation number/year (current query only)
    Q->>V: raw text hybrid query (dense 3-small + BM25)
    V-->>A: candidates
    A->>G: filter published/completed/verified/active-amended/canonical
    G->>R: fusion, heuristic rerank, relationship resolution, dedup+diversity
    R->>C: expansion, token budget, sufficiency guard
    C->>L: structured context + citation IDs + prompt version
    L-->>VF: answer + claims
    VF->>VF: extract, verify, citation validation (fail-closed)
    VF-->>U: answer + citations atau refusal
```

Hard filter (nomor/tahun/pasal) dari query saat ini; memory hanya soft signal.
Reranker tidak menggantikan hard filter. LLM tidak menentukan sumber sendiri.
Non-stream `/chat/ask` async: retrieval (60s) + generasi (80s) via
`asyncio.to_thread` (isolated session, total 140s di bawah middleware 150s,
504 + `stage` on timeout, outcome `timeout_retrieval`/`timeout_generation`);
stream memakai pola yang sama + heartbeat 15s. Evaluasi berat via Celery
(`kerjapedia.evaluation.run`), bukan BackgroundTasks.
