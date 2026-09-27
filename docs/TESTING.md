# Testing Guide

Task 11 membagi pengujian menjadi unit, integration, browser end-to-end, dan
acceptance performance. Target PRD untuk median response time adalah maksimal
5 detik.

## Backend

```powershell
cd apps/api
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check app tests
```

Unit test mencakup parser legal, chunker, metadata, embedding, retrieval,
formatter citation, answer generation, dan metrik evaluasi. Integration test
menggunakan FastAPI `TestClient` untuk autentikasi, chat, refusal, dokumen,
feedback, admin, ingestion, dan evaluasi.

Acceptance latency menjalankan sembilan request chat deterministik dan
memastikan median `latency_ms` tidak melewati 5.000 ms. Test lokal ini mengukur
pipeline aplikasi tanpa latency provider LLM eksternal; load test staging tetap
diperlukan sebelum rilis.

### Database integration lokal

Jalankan PostgreSQL test disposable, migration, dan pytest dengan satu perintah:

```powershell
.\scripts\test_api.ps1
```

Argumen setelah nama script diteruskan ke pytest. Gunakan `-KeepDatabase` bila container
perlu dipertahankan untuk investigasi. Database test memakai port `5433`, data disimpan di
`tmpfs`, dan selalu dipisahkan dari database development maupun production.

## Frontend quality gate

Job Web di GitHub Actions menjalankan pemeriksaan berikut secara berurutan:

```powershell
cd apps/web
npm ci
npm run lint
npm run build
npm run test:unit
npx playwright install chromium
npm run test:integration
npm run test:e2e
```

Suite unit mencakup berkas *.test.cjs. Suite integrasi menyalakan server Next.js
sementara dan menjalankan berkas *-browser.cjs berurutan. Job API menjalankan
Ruff, migrasi naik/turun, dan pytest dengan PostgreSQL uji.

## Frontend End-to-End

Pasang browser Playwright satu kali:

```powershell
cd apps/web
npx playwright install chromium
```

Jalankan skenario chat:

```powershell
npm run test:e2e
```

Playwright menjalankan Next.js otomatis pada `http://127.0.0.1:3100`. Respons
API dimock secara deterministik untuk menguji rendering jawaban, citation, pasal,
dan refusal. Contract backend yang sebenarnya divalidasi terpisah oleh integration
test agar kegagalan dapat dilokalisasi dengan jelas.
