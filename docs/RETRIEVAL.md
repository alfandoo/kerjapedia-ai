# Retrieval and Ranking

Task 5 mengimplementasikan retrieval lokal berbasis artifact ingestion. Engine ini membaca `chunks.json` dan `embeddings.json` dari `storage/ingestion/`, sehingga bisa berjalan tanpa PostgreSQL saat development.

## Command

Jalankan dari `apps/api`:

```bash
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Pastikan minimal satu dokumen sudah di-ingest:

```bash
.venv\Scripts\python -m app.services.ingestion.cli --document-id UU-21-2000
```

## Pipeline

1. Query understanding:
   - normalisasi query
   - deteksi topik
   - deteksi intent
   - ekspansi singkatan seperti `PKWT`, `PHK`, `THR`, `JHT`, `JKK`, `JKP`, dan `K3`
   - filter artikel, tahun, topik, jenis peraturan, dan status
2. Lexical search:
   - token matching dengan scoring BM25-lite
3. Semantic search:
   - cosine similarity terhadap embedding chunk
   - default memakai `local-hash-embedding-v1`
4. Hybrid retrieval:
   - Reciprocal Rank Fusion dari ranking lexical dan semantic
5. Reranking:
   - kombinasi fusion, lexical, semantic, overlap term, topic match, article match, dan status penalty
6. Context expansion:
   - mengambil chunk tetangga dalam dokumen/pasal/halaman terkait
7. Guardrail:
   - `should_refuse` aktif jika tidak ada chunk melewati threshold
   - warning muncul jika sumber `needs_verification`, historical, atau revoked

## Output

Response berisi:

- query asli dan query rewrite
- topik dan intent terdeteksi
- daftar chunk terpilih
- lexical, semantic, fusion, rerank, dan final score
- metadata hukum
- warning status sumber
- refusal reason bila konteks tidak cukup

## Catatan

Engine ini adalah retrieval baseline. Saat PostgreSQL + pgvector aktif, loader artifact dapat diganti dengan repository database tanpa mengubah kontrak `RetrievalDocument` dan `RetrievalResponse`.
