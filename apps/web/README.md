# Web KerjaPedia AI

Frontend Next.js untuk chat peraturan ketenagakerjaan, pencarian dokumen, kalkulator, tinjauan CV, kepatuhan, dan dashboard admin. Fitur berada di `src/features/`; rute dan proxy backend berada di `src/app/`.

## Pengembangan

Gunakan Node.js 22 dan jalankan API di `http://127.0.0.1:8000`, atau tetapkan `API_INTERNAL_URL` ke alamat API lain. Dari folder ini:

```powershell
npm ci
npm run dev
```

Buka `http://localhost:3000`. Proxy `/api/backend` meneruskan request ke API. Setup database dan migrasi dijelaskan di [README utama](../../README.md).

## Pemeriksaan

```powershell
npm run lint
npm run build
npm run test:unit
npx playwright install chromium
npm run test:integration
npm run test:e2e
```

`test:integration` memakai server Next.js sementara; `test:e2e` menjalankan Playwright. Semua perintah dijalankan oleh job `Web` di GitHub Actions. Lihat [panduan pengujian](../../docs/TESTING.md).
