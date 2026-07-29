"use client";

import Link from "next/link";
import { ScaleIcon } from "@/components/icons";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { login, register, SESSION_STORAGE_KEY } from "@/lib/api";

function RegisterPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSignup = searchParams.get("mode") === "signup";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setStatus(null);
    try {
      const session = isSignup
        ? await register(name.trim(), email.trim(), password)
        : await login(email.trim(), password);
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
      window.dispatchEvent(new Event("kerjapedia-session-change"));
      router.push("/chat");
    } catch (err) {
      setStatus((err as Error).message || "Gagal. Coba lagi.");
      setLoading(false);
    }
  }

  return (
    <div className="auth-standalone-page">
      <div className="auth-standalone-card">
        <div className="auth-standalone-brand">
          <ScaleIcon className="icon" />
          <span>KerjaPedia AI</span>
        </div>
        <h1>{isSignup ? "Daftar gratis" : "Masuk"}</h1>
        <p className="auth-standalone-desc">
          {isSignup
            ? "Buat akun agar percakapan dan riwayat Anda tetap tersedia."
            : "Masuk untuk melanjutkan menggunakan KerjaPedia AI."}
        </p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {isSignup ? (
            <>
              <label htmlFor="reg-name">Nama lengkap</label>
              <input
                id="reg-name"
                type="text"
                autoComplete="name"
                minLength={2}
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </>
          ) : null}
          <label htmlFor="reg-email">Email</label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="reg-password">Password</label>
          <div className="auth-password-field">
            <input
              id="reg-password"
              type={showPassword ? "text" : "password"}
              autoComplete={isSignup ? "new-password" : "current-password"}
              minLength={isSignup ? 8 : 1}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              type="button"
              className="auth-password-toggle"
              aria-label={showPassword ? "Sembunyikan password" : "Tampilkan password"}
              onClick={() => setShowPassword((prev) => !prev)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                <circle cx="12" cy="12" r="2.8" />
                {showPassword ? <path d="m4 4 16 16" /> : null}
              </svg>
            </button>
          </div>
          <button className="send-button" type="submit" disabled={loading}>
            {loading ? "Memproses..." : isSignup ? "Buat akun" : "Masuk"}
          </button>
          <p className="auth-mode-switch">
            {isSignup ? "Sudah punya akun? " : "Belum punya akun? "}
            <Link href={isSignup ? "/register" : "/register?mode=signup"}>
              {isSignup ? "Masuk" : "Daftar gratis"}
            </Link>
          </p>
          <p className="auth-mode-switch" style={{ marginTop: 4 }}>
            <Link href="/login-admin">Login sebagai admin</Link>
          </p>
          {status ? <p className="form-status">{status}</p> : null}
        </form>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterPageContent />
    </Suspense>
  );
}
