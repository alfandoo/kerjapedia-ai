# Backend API

OpenAPI tersedia di `/docs` dan `/openapi.json` ketika API dijalankan.

## Kuota token chat

- `GET /chat/usage` mengembalikan penggunaan identitas saat ini: `usage_date`, `timezone`, `reset_at`, `limit_tokens`, `prompt_tokens`, `completion_tokens`, `used_tokens`, `reserved_tokens`, `remaining_tokens`, dan `estimated_tokens`. Guest wajib mengirim header guest ID yang sama dengan chat.
- `POST /chat/ask` dan `POST /chat/ask/stream` memeriksa dan mencadangkan kuota sebelum model dipanggil. Keduanya mengembalikan HTTP 429 dengan `detail.code = daily_token_quota_exceeded`, `detail.reset_at`, dan header `Retry-After` ketika kapasitas tidak cukup.
- Hari kuota mengikuti Asia/Jakarta dan berganti pada 00.00 WIB. Batas default adalah 20.000 token guest dan 100.000 token akun, dapat diatur lewat `GUEST_DAILY_TOKEN_LIMIT` dan `USER_DAILY_TOKEN_LIMIT`. Total mencakup prompt dan completion.
- `GET /admin/stats` menyediakan `usage.today.provider_tokens` dan `usage.today.estimated_tokens`, dan `usage.today.unattributed_tokens` untuk membedakan angka provider, estimasi, dan total lama yang belum dapat diatribusikan.

## System dan chat

- `GET /health`: liveness dan konfigurasi provider nonsecret.
- `GET /ready`: readiness Neon PostgreSQL, Upstash Vector, Supabase Storage
  (production), Redis (bila Celery aktif), dan active release.
- `GET /metrics`: Prometheus exporter (tidak masuk OpenAPI).
- `POST /chat/ask`: jawaban terverifikasi nonstreaming.
- `POST /chat/ask/stream`: status proses, satu delta jawaban setelah verification, lalu event final.
- Request chat menerima `reasoning_mode` opsional: `fast`, `standard` (default), atau `deep`.
- Stream yang ditutup klien membatalkan panggilan provider yang masih berjalan. Turn dicatat
  sebagai `cancelled`, jawaban tidak disimpan, dan token provider yang sudah diketahui tetap dihitung.
- `GET /admin/metrics` menyediakan `by_mode` untuk `fast`, `standard`, dan `deep`: waktu
  ke status/konten pertama, latensi total, token, disconnect rate, retry, dan kegagalan provider.
- Reasoning internal selalu disembunyikan; klien hanya menerima status proses dan jawaban final.
- Endpoint conversation tetap kompatibel dengan frontend.

Request chat tanpa bearer token wajib mengirim `X-KerjaPedia-Guest-ID` berupa UUID.
Header yang hilang atau tidak valid menghasilkan HTTP 400; conversation milik guest lain
menghasilkan HTTP 403. Hanya satu turn per conversation dapat diproses sekaligus dan
request yang bertabrakan menghasilkan HTTP 409 `conversation_turn_in_progress`.

Kegagalan provider RAG mengembalikan HTTP 503 dengan `code`, pesan generik, dan
`trace_id`. Public answer debug tidak mengungkap prompt atau internal retrieval trace.

## Personalized Mode RAG

- Pengguna yang login dapat membaca GET /auth/work-profile, mengganti empat fakta opsional melalui PUT /auth/work-profile, dan menghapusnya melalui DELETE /auth/work-profile. Field: province, employment_status (PKWT/PKWTT), start_date (ISO date), monthly_wage (rupiah bulanan).
- Saat membuat percakapan, POST /chat/ask dan /chat/ask/stream menerima personalized_mode opsional. Default false; guest tidak dapat mengaktifkannya. PATCH /chat/conversations/{id}/personalized-mode mengubah percakapan milik akun. Respons detail dan ringkasan percakapan memuat status ini.
- Saat mode aktif, backend memakai fakta profil untuk query retrieval dan konteks jawaban. Fakta eksplisit pada pertanyaan terbaru mengungguli profil tersimpan untuk turn itu. Upah tidak dimasukkan ke query retrieval; fakta profil dikirim ke penyedia LLM saat generasi jawaban dan dipisahkan dari kutipan regulasi. Mode ini tidak mengubah profil secara otomatis.
- GET /chat/export menyertakan profil kerja milik pengguna. Menghapus profil atau akun menghapus fakta kerja tersimpan.

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
