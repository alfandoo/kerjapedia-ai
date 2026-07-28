"use client";

import { ScaleIcon } from "@/components/icons";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { login, SESSION_STORAGE_KEY } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
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
      const session = await login(email.trim(), password);
      if (!session.user.roles.includes("admin")) {
        setStatus("Akses ditolak. Hanya admin yang dapat masuk.");
        setLoading(false);
        return;
      }
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
      window.dispatchEvent(new Event("kerjapedia-session-change"));
      router.push("/admin/dashboard");
    } catch (err) {
      const message = (err as Error).message;
      setStatus(message || "Gagal. Coba lagi.");
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
        <div className="admin-login-badge">Admin</div>
        <h1>Masuk</h1>
        <p className="auth-standalone-desc">
          Masuk dengan akun admin untuk mengelola knowledge base.
        </p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <div className="auth-password-field">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
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
            {loading ? "Memeriksa..." : "Masuk"}
          </button>
          {status ? <p className="form-status">{status}</p> : null}
        </form>
      </div>
    </div>
  );
}
