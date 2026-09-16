# Backend API

OpenAPI tersedia di `/docs` dan `/openapi.json` ketika API dijalankan.

## System dan chat

- `GET /health`: liveness dan konfigurasi provider nonsecret.
- `GET /ready`: readiness database, Pinecone, Supabase, Redis, dan active immutable
  release.
- `GET /metrics`: Prometheus exporter (tidak masuk OpenAPI).
- `POST /chat/ask`: jawaban terverifikasi nonstreaming.
- `POST /chat/ask/stream`: status proses, lalu answer delta hanya setelah verification.
- Endpoint conversation tetap kompatibel dengan frontend.

Request chat tanpa bearer token wajib mengirim `X-KerjaPedia-Guest-ID` berupa UUID.
Header yang hilang atau tidak valid menghasilkan HTTP 400; conversation milik guest lain
menghasilkan HTTP 403. Hanya satu turn per conversation dapat diproses sekaligus dan
request yang bertabrakan menghasilkan HTTP 409 `conversation_turn_in_progress`.

Kegagalan provider RAG mengembalikan HTTP 503 dengan `code`, pesan generik, dan
`trace_id`. Public answer debug tidak mengungkap prompt atau internal retrieval trace.

## Dokumen dan ingestion

- Endpoint `/documents` menyediakan registry dan PDF/citation publik.
- Lookup governance admin menggunakan registry gabungan dataset resmi dan upload
  manifest, sehingga candidate hasil upload mengikuti verification/publication gate
  yang sama.
- `POST /ingestion/jobs` membuat job checksum-idempotent; `GET /ingestion/jobs` dan
  `GET /ingestion/jobs/{id}` membaca status.
- `POST /admin/documents/{id}/verification` mencatat source/legal verification audit.
- `POST /admin/documents/{id}/publication` mengubah publication status; publish hanya
  untuk candidate version yang source-verified dan legal-reviewed. Candidate baru
  menjadi current saat release dipromosikan.
- `PUT /admin/documents/{id}/relationships` mengganti normalized legal relationships
  beserta reviewer, pasal, dan evidence URL.

## Immutable RAG releases

- `GET/POST /admin/rag/releases`: list atau buat snapshot release.
- `POST /admin/rag/releases/{id}/build`: queue pembangunan namespace.
- `POST /admin/rag/releases/{id}/transition`: `validate`, `promote`, atau `retire`.

Validation membutuhkan evaluation run milik release yang sama dan seluruh gate harus
lulus. Promotion mengganti active namespace secara atomik; mempromosikan release retired
menjadi mekanisme rollback.

## Evaluation

- `POST /evaluation/datasets`: buat dataset maksimal 500 kasus.
- `POST /evaluation/datasets/{dataset_id}/questions/{question_id}/review`: append-only
  review event oleh role `legal_reviewer`.
- `POST /evaluation/datasets/seed`: impor 150 seed nonproduksi.
- `POST /evaluation/runs` (202): tanpa `release_id` menjalankan eksperimen artifact;
  dengan `release_id` menjalankan stack production terhadap namespace tersebut. Run
  berjalan asinkron di latar: respons langsung berisi status `pending`, progres
  dipolling via `GET /evaluation/runs` dan `GET /evaluation/runs/{id}` hingga
  `completed`/`failed`.

Release evaluation membutuhkan minimal 300 kasus human-verified dengan split
`development` dan `test`, serta audit event review terbaru yang verified untuk setiap
pertanyaan.
