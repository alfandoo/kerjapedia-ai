# Security, Privacy, and Reliability

Production menolak startup bila memakai provider development, sumber unpublished,
fallback terbuka, Celery nonaktif, password admin lemah, atau CORS localhost. Credential
selalu berasal dari environment dan tidak boleh dicatat atau di-commit.

Prompt memperlakukan PDF sebagai untrusted data. Input injection yang eksplisit diblokir;
structured citation IDs divalidasi terhadap retrieval; claim verifier memeriksa setiap
klaim. Provider failure menghasilkan error terstruktur dengan trace ID dan tidak
menampilkan exception/provider detail ke pengguna.

Trace server hanya menyimpan hash retrieval query, model/prompt/answer version,
chunk/document version, score, verification result, jumlah redaksi PII, dan token usage.
Email, nomor telepon, NIK, serta token eksplisit disamarkan sebelum query memory dikirim
ke embedding/Pinecone. System prompt,
rendered prompt, serta query kontekstual mentah tidak masuk response publik. Celery Beat
menghapus `rag_trace` setelah `RAG_TRACE_RETENTION_DAYS` (default 30).

Chat guest wajib memakai UUID per browser dan conversation tidak pernah dibuat tanpa
owner. Urutan message dialokasikan per conversation di bawah row lock singkat; pending
turn mencegah request bersamaan mencampur konteks dan dapat dipulihkan setelah timeout.

`/health` digunakan sebagai liveness. `/ready` gagal ketika database/Pinecone tidak siap,
tidak ada active release, atau registry membuat snapshot release stale. Prometheus
tersedia di `/metrics`; OpenTelemetry OTLP bersifat opsional melalui environment.

Review hukum dokumen dan golden question memerlukan role `legal_reviewer`. Status review
evaluasi tidak dipercaya dari payload pembuatan dataset; setiap perubahan disimpan
sebagai audit event append-only.

Upload admin dibatasi PDF 50 MB dengan signature `%PDF-`. Ingestion dan build release
berjalan sebagai Celery job durable/idempotent. Namespace aktif immutable dan promosi
release dijaga transaksi serta unique constraint.

Pekerjaan platform yang masih terpisah dari hardening RAG ini: auth browser berbasis
HttpOnly cookie, distributed rate limiting, backup/restore terjadwal, dan kebijakan
retensi keseluruhan conversation/feedback.
