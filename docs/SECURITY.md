# Security, Privacy, and Reliability

## Secret dan Konfigurasi

Semua credential provider dibaca dari environment variable. File `.env` dan artifact
lokal diabaikan Git; `.env.example` hanya memuat nama variabel dan nilai development.
Saat `APP_ENV=production`, aplikasi menolak startup bila password admin masih default,
credential provider aktif belum tersedia, atau CORS masih menunjuk localhost.

## Authentication

Session menggunakan token acak 256-bit dan memiliki masa berlaku yang dikontrol oleh
`SESSION_TTL_MINUTES`. Role admin hanya diberikan ketika email dan password cocok dengan
`ADMIN_EMAIL` dan `ADMIN_PASSWORD`; prefix email tidak menentukan role.

Konfigurasi ini masih merupakan autentikasi MVP satu-admin. Deployment multi-user harus
mengganti credential tunggal dengan identity provider atau tabel user yang menyimpan
password menggunakan Argon2id.

## API dan Upload

- Rate limit dasar diterapkan per alamat client.
- Setiap respons memiliki request ID, latency, dan security headers.
- CORS dikontrol melalui `CORS_ORIGINS`.
- Upload admin hanya menerima file dengan extension `.pdf`, signature `%PDF-`, dan
  ukuran maksimum 50 MB.
- Request Groq dan koneksi database memiliki timeout terbatas.

## RAG Guardrail

Prompt `kerjapedia-grounded-answer-v2` memperlakukan isi dokumen sebagai data tidak
tepercaya dan mengabaikan instruksi yang tertanam di dalamnya. Citation model divalidasi
terhadap chunk hasil retrieval. Jika retrieval kosong, citation tidak valid, atau LLM
gagal, service melakukan refusal atau fallback berbasis sumber.

## Logging dan Retention

Log request memuat request ID, path, method, status, latency, dan client; body pertanyaan,
password, token, dan API key tidak boleh dicatat. Trace jawaban memuat versi prompt,
model, dan ID chunk untuk audit.

Untuk MVP, riwayat chat dan feedback berada di memory dan hilang saat service restart.
Ketika persistensi production diaktifkan, default retention adalah 90 hari untuk riwayat
chat dan feedback, serta 30 hari untuk application log. Penghapusan lebih awal atas
permintaan pengguna harus didukung sebelum peluncuran publik.

## Pekerjaan Tersisa

- Auth multi-user dengan identity provider atau password hash Argon2id.
- Rate limiter terdistribusi melalui Redis untuk deployment multi-instance.

## Retry Ingestion

CLI ingestion mengulang kegagalan transien seperti timeout, gangguan koneksi, rate-limit,
dan respons provider 5xx. Default-nya dua retry dengan exponential backoff:

```powershell
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021 `
  --max-retries 2 --retry-delay 1
```

Error permanen, misalnya metadata invalid, tidak diulang. Artifact memakai versi checksum
deterministik dan Pinecone mengganti vector pada versi yang sama sebelum upsert, sehingga
retry tidak meninggalkan chunk duplikat.

## Backup PostgreSQL

Backup metadata menggunakan format custom `pg_dump`, membuat checksum SHA-256, dan
menyimpan hasil di `storage/backups/postgres/` yang diabaikan Git:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1
```

Untuk sekaligus membuat database sementara, melakukan restore, memeriksa tabel, lalu
menghapus database pemeriksaan:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1 -VerifyRestore
```

Backup lama dihapus setelah 14 hari secara default. Gunakan `-RetentionDays` untuk
mengubah kebijakan. Script membatasi lokasi backup agar tetap berada di workspace dan
hanya menghapus file dengan pola backup KerjaPedia.
