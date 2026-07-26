# Retrieval and Ranking

Task 5 mengimplementasikan retrieval lokal berbasis artifact ingestion. Mode industri menambahkan retrieval Pinecone melalui kontrak response yang sama, sehingga API dan frontend tidak berubah.

## Command

Jalankan dari `apps/api`:

```bash
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Untuk retrieval Pinecone:

```bash
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone
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
   - ekspansi istilah waktu seperti `batas waktu` menjadi frasa legal `paling lambat`
     dan `wajib dibayarkan`
   - filter artikel, tahun, topik, jenis peraturan, dan status
2. Lexical search:
   - token matching dengan scoring BM25-lite
3. Semantic search:
   - cosine similarity terhadap embedding chunk
   - mode lokal memakai artifact embedding
   - mode industri memakai minimal 100 kandidat Pinecone dari BGE-M3 query
     embedding sebelum lexical reranking
4. Hybrid retrieval:
   - Reciprocal Rank Fusion dari ranking lexical dan semantic
5. Reranking:
   - kombinasi fusion, lexical, semantic, overlap term, topic match, article match, dan status penalty
6. Context expansion:
   - mengambil chunk tetangga dalam dokumen/pasal/halaman terkait
7. Guardrail:
   - `should_refuse` aktif jika tidak ada chunk melewati threshold
   - query di luar domain ketenagakerjaan ditolak dengan `out_of_scope_query`
     sebelum embedding dan answer generation
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

Engine lokal tetap menjadi fallback development. Untuk mode industri, `PineconeRetrievalStore` membuat/membaca index Pinecone serverless dan mengembalikan `RetrievalDocument` serta `RetrievalResponse` yang sama dengan mode artifact.
