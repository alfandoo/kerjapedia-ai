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
