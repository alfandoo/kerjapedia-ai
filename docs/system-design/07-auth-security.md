# 07 — Auth & Security

Auth: Google ID token → Supabase Auth (`sign_in_with_id_token`); email/password
+ OTP deferred signup (Fernet + HMAC, 8 digit, 15 mnt, max 8 attempts).
Backend Bearer authority (`dependencies.py`); roles `admin/legal_reviewer/user/
guest`; data protection di API (`require_admin` 403).
Session: Next.js BFF (`app/api/backend/[...path]`) memegang token di HttpOnly
`__Host-kp-access/refresh` (Secure prod, SameSite Lax, CSRF origin + header,
tanpa forward Authorization/Cookie). Guard berlapis: `proxy.ts` redirect
`/admin/*` tanpa cookie → `app/admin/layout.tsx` server presence guard →
`AdminShell` client role redirect; `login-admin` revoke sesi non-admin via
`signOut`. `login-methods` dibatasi 10/min + validasi email di BFF + backend.

Security: CORS allowlist (tanpa localhost di prod), HSTS prod, nosniff/DENY/
no-referrer, 50MB PDF guard + `%PDF-` magic, path traversal via `Path.name`,
signed URL untuk bucket private, rate-limit 60/min identity + 600/min IP,
login-methods bounded (user enumeration risk — batasi di WAF), PII redaction
(NIK/phone/NPWP), tidak log secrets/CV mentah, prompt-injection gate di
ingestion, publication gate (completed+verified+canonical go.id).
