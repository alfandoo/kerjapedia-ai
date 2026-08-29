# KerjaPedia AI — Production MVP Industry Readiness Audit

**Tanggal audit:** 28 Agustus 2026
**Baseline:** commit `531bf3e` pada branch `codex/kerjapedia-rag-chat`
**Target:** Production MVP untuk tim kecil
**Kesimpulan:** **belum siap produksi**

## 1. Ringkasan eksekutif

KerjaPedia AI sudah memiliki fondasi yang lebih matang daripada prototipe biasa:
monorepo memisahkan web dan API, backend memiliki service ingestion/retrieval/answering,
database memakai migration, image container berjalan sebagai non-root, prompt dan citation
memiliki model terstruktur, serta terdapat 82 test backend dan 19 test E2E yang masuk ke
`testDir` Playwright.

Namun repository belum memenuhi standar Production MVP. Blocker utamanya bukan pilihan
framework, melainkan quality gate yang merah, test yang tidak terisolasi, konfigurasi yang
tidak dapat direproduksi dari repository, penyimpanan token browser yang rentan terhadap
XSS, health check yang dapat memberi status sehat saat dependency gagal, dan workflow
status hukum yang tidak otomatis menyinkronkan metadata ke vector store.

### Penilaian per area

| Area                       | Status        | Ringkasan                                                                                                                                           |
| -------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Arsitektur dan struktur    | **Partial**   | Batas aplikasi dan service cukup jelas, tetapi beberapa modul berukuran 400–850 baris dan `packages/` belum digunakan.                              |
| Quality engineering        | **Not Ready** | TypeScript dan Ruff lulus; ESLint gagal, Prettier gagal pada 74 file, test backend tidak terisolasi, dan tidak ada coverage gate.                   |
| Security dan reliability   | **Not Ready** | Auth memakai Supabase, tetapi token berada di `localStorage`; rate limit in-memory; startup dan health menyembunyikan dependency failure.           |
| Build dan deployment       | **Not Ready** | Container production cukup baik, tetapi environment template hilang, local Compose tidak sesuai README, dan job CI API tidak menyediakan database.  |
| RAG dan legal governance   | **Partial**   | Citation, refusal, prompt versioning, dan evaluasi tersedia; provenance verifikasi hukum dan sinkronisasi status ke Pinecone belum aman.            |
| Dokumentasi dan governance | **Not Ready** | Dokumentasi luas tetapi beberapa bagian material sudah stale; belum ada ownership, contribution, dependency update, atau security reporting policy. |

## 2. Metode dan bukti

Audit dilakukan secara statis tanpa menjalankan dev server atau browser. Perintah berikut
digunakan terhadap worktree bersih pada baseline audit.

| Pemeriksaan                                 | Hasil aktual                                                                                |
| ------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `npx tsc --noEmit --incremental false`      | **Lulus**                                                                                   |
| `npm run lint`                              | **Gagal:** 3 error dan 7 warning                                                            |
| `npm run format:check`                      | **Gagal:** 74 file tidak sesuai Prettier                                                    |
| `python -m ruff check --no-cache app tests` | **Lulus**                                                                                   |
| `python -m pytest ...`                      | **Tidak mencapai assertion:** fixture session mencoba membuka database Supabase dari `.env` |
| Playwright                                  | **Tidak dijalankan:** konfigurasi dan cakupan diperiksa secara statis                       |
| `git status --short`                        | Bersih sebelum dokumen audit dibuat                                                         |

Temuan juga diverifikasi melalui `.github/workflows/`, Dockerfile, Compose, migration,
konfigurasi test, model API, dataset metadata, dan dokumentasi teknis.

## 3. Temuan P0 — blocker produksi

### P0-1 — Quality gate frontend gagal

- **Bukti:** `npm run lint` gagal pada `app-shell.tsx`, `settings-modal.tsx`, dan
  `settings-provider.tsx`; terdapat tujuh warning lain. `npm run format:check` melaporkan
  74 file.
- **Dampak:** job CI web tidak dapat hijau; regresi React dan type escape `any` dapat masuk
  karena commit sebelumnya perlu melewati hook.
- **Akar masalah:** formatter belum diterapkan konsisten dan pre-commit menjalankan seluruh
  lint yang sudah merah tanpa baseline yang dibersihkan.
- **Acceptance criteria:** ESLint, Prettier check, TypeScript, dan build lulus dari checkout
  bersih; pre-commit dan CI menjalankan perintah identik.
- **Ukuran:** **S**.
- **Dependensi:** dikerjakan pertama sebelum refactor lain.

### P0-2 — Test backend tidak terisolasi dan CI tidak menyediakan database

- **Bukti:** fixture session di `apps/api/tests/conftest.py` selalu memanggil
  `ensure_schema()` sebelum test. Settings membaca `.env` developer; pada audit, pytest
  mencoba database Supabase. Job API di `.github/workflows/ci.yml` tidak mendefinisikan
  service PostgreSQL maupun `DATABASE_URL` test.
- **Dampak:** test dapat gagal karena jaringan, menyentuh database non-test, atau memberi
  hasil berbeda antara laptop dan CI. Ini juga merupakan risiko integritas data.
- **Akar masalah:** tidak ada settings profile khusus test dan database fixture bersifat
  global.
- **Acceptance criteria:** test memaksa database disposable dengan nama/credential test,
  menolak host production, menjalankan migration, membersihkan data, dan lulus di CI tanpa
  secret eksternal.
- **Ukuran:** **M**.
- **Dependensi:** membutuhkan service PostgreSQL CI atau testcontainer; selesaikan sebelum
  menjadikan pytest required check.

### P0-3 — Kontrak environment dan local development rusak

- **Bukti:** README menyuruh menyalin `.env.example` dan `.env.production.example`, tetapi
  tidak ada template environment yang tracked. README dan `docs/ARCHITECTURE.md` menyebut
  PostgreSQL, Redis, dan MinIO pada `compose.yaml`; file tersebut hanya menyediakan Redis.
- **Dampak:** engineer baru tidak dapat menjalankan stack sesuai dokumentasi; deployment
  mudah memakai default yang salah atau secret yang tidak lengkap.
- **Akar masalah:** konfigurasi dan dokumentasi berevolusi terpisah, sementara template
  environment pernah dihapus.
- **Acceptance criteria:** template tanpa secret tersedia dan divalidasi; Compose lokal
  sesuai dokumen atau dokumen secara eksplisit menjelaskan dependency managed; satu smoke
  command membuktikan setup dari checkout bersih.
- **Ukuran:** **M**.
- **Dependensi:** selaraskan dengan keputusan database/object storage lokal pada P0-2.

### P0-4 — Access dan refresh token disimpan di `localStorage`

- **Bukti:** `apps/web/src/features/auth/api.ts` dan `apps/web/src/features/auth/session.ts`, halaman login/register, dan auth modal membaca dan
  menulis seluruh `UserSession` ke `localStorage`, termasuk refresh token.
- **Dampak:** XSS pada origin dapat mengambil token jangka panjang dan mengambil alih sesi,
  termasuk sesi admin.
- **Akar masalah:** frontend memakai bearer-token SPA tanpa backend-for-frontend atau cookie
  session.
- **Acceptance criteria:** refresh token berada pada cookie `HttpOnly`, `Secure`, dan
  `SameSite`; access token tidak persisten di JavaScript storage; CSRF, logout, rotation,
  expiry, dan admin session diuji.
- **Ukuran:** **L**.
- **Dependensi:** keputusan session architecture dan perubahan auth contract.

### P0-5 — Health check memberi false positive

- **Bukti:** `/health` selalu mengembalikan `status="ok"` dan HTTP 200 walaupun
  `pinecone_ready` atau `supabase_auth` gagal. Startup menangkap exception schema dan
  Supabase lalu tetap melayani traffic. Compose production menggunakan health endpoint ini
  untuk menandai API sehat.
- **Dampak:** orchestrator dapat mengirim traffic ke instance yang tidak mampu melakukan
  auth, retrieval, atau persistensi.
- **Akar masalah:** liveness dan readiness digabung dan dependency wajib tidak dimodelkan.
- **Acceptance criteria:** `/live` hanya memeriksa proses; `/ready` mengembalikan non-2xx
  ketika dependency wajib gagal; Compose memakai readiness; error startup dan provider
  memiliki log serta metric yang dapat ditindaklanjuti.
- **Ukuran:** **M**.
- **Dependensi:** definisi dependency wajib per mode local/production.

### P0-6 — Status hukum dan vector metadata dapat berbeda

- **Bukti:** PATCH admin dokumen memperbarui manifest dan override database, tetapi tidak
  menjadwalkan update/reindex Pinecone. Warning jawaban dibangun dari metadata hasil
  retrieval. Saat audit, seluruh 19 dokumen berstatus `active`/`verified`, sedangkan empat
  catatan relasi masih secara eksplisit meminta verifikasi.
- **Dampak:** UI admin dapat menunjukkan status baru sementara jawaban memakai status lama;
  label “verified” juga tidak membuktikan pemeriksaan hukum substantif.
- **Akar masalah:** status dokumen diperlakukan sebagai field editable biasa tanpa workflow,
  reviewer evidence, atau outbox sinkronisasi vector store.
- **Acceptance criteria:** perubahan status menyimpan reviewer, waktu, dasar/sumber, dan
  audit event; sinkronisasi vector bersifat idempotent dan observable; UI memperlihatkan
  `pending/synced/failed`; test membuktikan warning berubah setelah sync. Status `verified`
  hanya dapat diberikan melalui workflow review.
- **Ukuran:** **L**.
- **Dependensi:** schema/audit migration, job/outbox, dan kebijakan legal review.

## 4. Temuan P1 — reliability dan maintainability

### P1-1 — Startup schema bercampur dengan migration

- **Bukti:** API memanggil SQLAlchemy `create_all()` pada lifespan, sementara deployment
  juga memiliki service Alembic migration; kegagalan startup schema ditelan.
- **Dampak:** drift schema dapat tersembunyi dan failure baru terlihat ketika request masuk.
- **Acceptance criteria:** production hanya memakai Alembic; startup memverifikasi revision
  database dan gagal cepat bila incompatible.
- **Ukuran:** **S**. **Dependensi:** P0-2 dan P0-5.

### P1-2 — Rate limiter tidak production-safe

- **Bukti:** counter disimpan dalam dictionary process-local di `app/api/state.py`, memakai
  lock thread, dan tidak memiliki pruning key.
- **Dampak:** limit berbeda per replica, hilang saat restart, dapat menumbuhkan memory, dan
  tidak andal di belakang proxy.
- **Acceptance criteria:** limiter Redis dengan key TTL, trusted proxy policy, limit per
  user/IP, serta test multi-instance dan retry header.
- **Ukuran:** **M**. **Dependensi:** Redis contract pada P0-3.

### P1-3 — Modul UI dan route terlalu besar

- **Bukti:** `admin-dashboard.tsx` sekitar 858 baris, `chat-workspace-shell.tsx` 701,
  `admin-evaluation.tsx` 593, `lib/api.ts` 528, `routes_admin.py` 462, dan
  `conversation-thread.tsx` 441.
- **Dampak:** review sulit, ownership kabur, unit test mahal, dan perubahan UI mudah saling
  menimpa.
- **Acceptance criteria:** pisahkan container/state, presentational component, API client,
  schema, dan feature module; tetapkan batas ukuran sebagai guideline, bukan sekadar angka
  lint.
- **Ukuran:** **L**. **Dependensi:** quality gate hijau dan test characterization.

### P1-4 — Kontrak frontend/backend diduplikasi manual

- **Bukti:** response model Pydantic di API ditulis ulang sebagai banyak type pada
  type per feature di `apps/web/src/features/*/types.ts`; tidak ada OpenAPI code generation atau runtime validation.
- **Dampak:** perubahan response dapat lolos compile salah satu sisi dan gagal saat runtime.
- **Acceptance criteria:** OpenAPI menjadi source of truth, client/type dihasilkan dalam CI,
  response kritis divalidasi, dan breaking-change check tersedia.
- **Ukuran:** **M**. **Dependensi:** API schema harus distabilkan setelah P0-4/P0-6.

### P1-5 — Cakupan test tidak seimbang dan tidak diukur

- **Bukti:** tersedia 82 test backend dan 19 E2E di `tests/e2e`; dua test pada
  `tests/search.qa.ts` berada di luar `testDir` Playwright sehingga tidak dijalankan oleh
  script default. Tidak ada framework unit/component frontend dan tidak ada coverage gate.
- **Dampak:** logic hook, localization, renderer, auth refresh, dan state modal hanya
  terdeteksi melalui E2E yang lebih lambat atau tidak diuji.
- **Acceptance criteria:** pindahkan/daftarkan semua E2E, tambah unit/component test untuk
  logic kritis, laporkan coverage per layer, dan tetapkan threshold realistis bertahap.
- **Ukuran:** **M**. **Dependensi:** P0-1 dan P0-2.

### P1-6 — Dependency Python belum reproducible

- **Bukti:** `requirements.txt` mencampur exact pin dan range seperti `groq>=`,
  `pinecone>=`, `sentence-transformers>=`, dan `supabase>=`; tidak ada lock dengan hash.
- **Dampak:** build pada tanggal berbeda dapat menghasilkan dependency graph berbeda.
- **Acceptance criteria:** gunakan lock terpisah runtime/dev dengan hash, automated update,
  dan vulnerability/license scan di CI.
- **Ukuran:** **M**. **Dependensi:** tidak ada.

### P1-7 — Observability operasional belum cukup

- **Bukti:** tersedia request ID dan latency log, tetapi tidak ditemukan structured logging,
  metrics exporter, tracing, error tracking, alert, atau SLO. In-memory rate state juga tidak
  dapat diamati lintas replica.
- **Dampak:** kegagalan retrieval/provider dan penurunan kualitas sulit didiagnosis sebelum
  pengguna melapor.
- **Acceptance criteria:** JSON log terstruktur, redaction, latency/error/provider metrics,
  trace correlation, dashboard, dan alert untuk readiness, error rate, serta RAG refusal.
- **Ukuran:** **M**. **Dependensi:** P0-5.

### P1-8 — Dokumentasi material tidak sesuai implementasi

- **Bukti:** `docs/SECURITY.md` menjelaskan auth token acak dan single-admin password,
  sedangkan implementasi memakai Supabase dan role profile; dokumen tersebut menyebut prompt
  v2, `docs/ANSWER_GENERATION.md` v1, sementara kode memakai v4. Dokumen juga menyatakan
  chat/feedback in-memory walaupun model persistence tersedia.
- **Dampak:** operator dan reviewer keamanan membuat keputusan dari arsitektur yang salah.
- **Acceptance criteria:** docs diuji terhadap configuration contract, prompt version, auth,
  storage, dan runbook aktual; setiap perubahan arsitektur wajib memperbarui docs terkait.
- **Ukuran:** **M**. **Dependensi:** selesaikan keputusan P0 terlebih dahulu agar docs tidak
  langsung stale lagi.

## 5. Temuan P2 — kematangan engineering

### P2-1 — Pre-commit tidak portable

- **Bukti:** local hook menjalankan `powershell` dan path `.venv\\Scripts`, sementara CI
  berjalan di Ubuntu dengan perintah berbeda.
- **Dampak:** contributor non-Windows tidak mendapatkan gate yang sama.
- **Acceptance criteria:** command lint/test dibungkus task runner lintas platform dan dipakai
  identik oleh local hook serta CI.
- **Ukuran:** **S**. **Dependensi:** P0-1/P0-2.

### P2-2 — Governance repository belum lengkap

- **Bukti:** tidak ditemukan `CONTRIBUTING.md`, `LICENSE`, root security policy,
  `CODEOWNERS`, Dependabot/Renovate, atau release/changelog policy.
- **Dampak:** ownership, pelaporan vulnerability, dan proses perubahan tidak eksplisit.
- **Acceptance criteria:** tambahkan ownership, contribution/review policy, security contact,
  license decision, dependency automation, branch protection, dan release notes.
- **Ukuran:** **S**. **Dependensi:** keputusan pemilik repository.

### P2-3 — Struktur monorepo belum sepenuhnya disengaja

- **Bukti:** `packages/` hanya berisi `.gitkeep`; tidak ada root package/workspace manager,
  sementara kontrak bersama memang dibutuhkan.
- **Dampak:** struktur memberi ekspektasi shared package yang belum nyata dan command harus
  dijalankan manual per aplikasi.
- **Acceptance criteria:** hapus folder placeholder atau jadikan workspace nyata untuk
  generated API client/shared tooling; sediakan command root untuk verify/build/test.
- **Ukuran:** **S–M**. **Dependensi:** P1-4.

## 6. Kekuatan yang perlu dipertahankan

- Pemisahan `apps/web`, `apps/api`, `dataset`, `docs`, `evaluation`, dan `storage` sudah
  sesuai domain utama.
- Backend memisahkan ingestion, retrieval, answering, evaluation, dan provider adapters.
- Alembic migration, container multi-stage/non-root, healthcheck, backup script, smoke script,
  dan container CI sudah tersedia sebagai fondasi operasional.
- Pydantic response model, citation terstruktur, refusal/clarification, prompt version v4,
  Pinecone namespace, dan evaluation metrics memberi dasar auditability RAG yang baik.
- TypeScript strict dan Ruff aktif; 82 test backend mencakup API, auth/security, ingestion,
  retrieval, answering, citation, retry, upload, dan evaluation.
- `.env`, storage artifact, cache, test result, dan local database sudah diabaikan Git.

## 7. Roadmap perbaikan

### Fase 1 — Pulihkan quality gate dan test isolation

1. Bersihkan ESLint/Prettier dan samakan command local/CI.
2. Buat settings test yang fail-safe dan PostgreSQL disposable di CI.
3. Jalankan migration, seluruh pytest, TypeScript, lint, format, build, dan E2E smoke sebagai
   required checks.
4. Daftarkan dua test Playwright yang saat ini berada di luar `testDir`.

**Exit criteria:** setiap PR dapat diverifikasi dari checkout bersih tanpa credential atau
service production.

### Fase 2 — Amankan konfigurasi dan runtime production

1. Pulihkan environment template dan selaraskan Compose/README.
2. Pisahkan liveness/readiness dan fail-fast untuk dependency wajib.
3. Migrasikan session ke cookie HttpOnly dan tambah test security.
4. Ganti rate limiter dengan Redis dan definisikan trusted proxy.
5. Hilangkan `create_all()` dari startup production.

**Exit criteria:** deployment baru dapat direproduksi, instance gagal dependency tidak
menerima traffic, dan token jangka panjang tidak dapat dibaca JavaScript.

### Fase 3 — Stabilkan kontrak dan legal-data workflow

1. Tambah workflow verifikasi dengan reviewer evidence dan audit trail.
2. Sinkronkan perubahan metadata ke Pinecone melalui job/outbox idempotent.
3. Generate frontend client/types dari OpenAPI.
4. Pecah modul besar per feature setelah characterization test tersedia.
5. Lock dependency Python dan aktifkan dependency/security scan.

**Exit criteria:** status admin dan retrieval konsisten, perubahan kontrak terdeteksi CI,
dan feature utama dapat diuji tanpa membuka komponen raksasa.

### Fase 4 — Observability dan governance

1. Tambah structured log, metrics, tracing, dashboard, alert, dan SLO awal.
2. Perbarui seluruh docs terhadap arsitektur final dan tambah drift checks.
3. Tambah CODEOWNERS, contribution/security policy, dependency automation, branch
   protection, dan release procedure.
4. Putuskan fungsi `packages/` serta sediakan root task runner.

**Exit criteria:** insiden dapat dideteksi dan ditelusuri, ownership jelas, dan dokumentasi
operasional cocok dengan sistem yang berjalan.

## 8. Definition of Done Production MVP

Repository baru dapat dinilai **Ready** setelah seluruh P0 ditutup dan bukti berikut tersedia:

- Semua required check hijau dari checkout bersih.
- Test tidak pernah memakai database/provider production.
- Setup local dan production dapat dibuat dari template tracked tanpa secret contoh.
- Auth session, readiness, rate limit, migration, backup, restore, dan rollback memiliki test
  atau runbook yang telah diverifikasi.
- Status hukum mempunyai reviewer evidence dan konsisten sampai metadata retrieval.
- Dashboard/log dapat membedakan kegagalan aplikasi, database, auth, vector store, dan LLM.
- Dokumentasi arsitektur, security, prompt, deployment, serta testing sesuai implementasi.

Audit ini menilai engineering readiness. Label `verified` pada metadata tidak dianggap
sebagai bukti bahwa isi dan keberlakuan setiap regulasi telah diverifikasi secara hukum.
