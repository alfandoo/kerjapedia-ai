"use client";

import Link from "next/link";
import { ScaleIcon } from "@/components/icons";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { login, register, SESSION_STORAGE_KEY } from "@/features/auth/api";

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
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_50%_0,#f4fbfa_0,#fff_32rem)] p-6">
      <div className="w-full max-w-[400px] rounded-2xl border border-[#e5e5e5] bg-white p-[44px_36px_36px] shadow-[0_16px_40px_rgba(21,32,31,0.08)]">
        <div className="mb-7 flex items-center gap-2.5">
          <ScaleIcon className="size-[30px] [stroke-width:2] text-javanese" />
          <span className="text-xl font-bold text-tinta">KerjaPedia AI</span>
        </div>
        <h1 className="mb-2 font-display text-2xl font-semibold text-javanese">
          {isSignup ? "Daftar gratis" : "Masuk"}
        </h1>
        <p className="mb-7 text-sm leading-relaxed text-muted-text">
          {isSignup
            ? "Buat akun agar percakapan dan riwayat Anda tetap tersedia."
            : "Masuk untuk melanjutkan menggunakan KerjaPedia AI."}
        </p>
        <form className="grid gap-1.5" onSubmit={handleSubmit}>
          {isSignup ? (
            <>
              <label
                htmlFor="reg-name"
                className="mt-1 text-[13px] font-bold text-muted-text first:mt-0"
              >
                Nama lengkap
              </label>
              <input
                id="reg-name"
                type="text"
                autoComplete="name"
                minLength={2}
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 text-sm text-tinta outline-none transition focus:border-javanese focus:ring-2 focus:ring-javanese/10"
              />
            </>
          ) : null}
          <label
            htmlFor="reg-email"
            className="mt-1 text-[13px] font-bold text-muted-text first:mt-0"
          >
            Email
          </label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 text-sm text-tinta outline-none transition focus:border-javanese focus:ring-2 focus:ring-javanese/10"
          />
          <label
            htmlFor="reg-password"
            className="mt-1 text-[13px] font-bold text-muted-text first:mt-0"
          >
            Password
          </label>
          <div className="relative">
            <input
              id="reg-password"
              type={showPassword ? "text" : "password"}
              autoComplete={isSignup ? "new-password" : "current-password"}
              minLength={isSignup ? 8 : 1}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 pr-11 text-sm text-tinta outline-none transition focus:border-javanese focus:ring-2 focus:ring-javanese/10"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex items-center justify-center px-3 text-tinta transition hover:opacity-70"
              aria-label={showPassword ? "Sembunyikan password" : "Tampilkan password"}
              onClick={() => setShowPassword((prev) => !prev)}
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="size-[18px] fill-none stroke-current [stroke-linecap:round] [stroke-linejoin:round] [stroke-width:1.8]"
              >
                <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                <circle cx="12" cy="12" r="2.8" />
                {showPassword ? <path d="m4 4 16 16" /> : null}
              </svg>
            </button>
          </div>
          <button
            className="mt-5 h-[46px] w-full rounded-[10px] bg-javanese px-5 text-sm font-semibold text-white transition hover:bg-forest disabled:pointer-events-none disabled:opacity-60"
            type="submit"
            disabled={loading}
          >
            {loading ? "Memproses..." : isSignup ? "Buat akun" : "Masuk"}
          </button>
          <p className="mt-4 text-center text-xs text-muted-text">
            {isSignup ? "Sudah punya akun? " : "Belum punya akun? "}
            <Link
              href={isSignup ? "/register" : "/register?mode=signup"}
              className="font-semibold text-javanese transition hover:text-forest [text-underline-offset:3px]"
            >
              {isSignup ? "Masuk" : "Daftar gratis"}
            </Link>
          </p>
          <p className="mt-4 text-center text-xs text-muted-text" style={{ marginTop: 4 }}>
            <Link
              href="/login-admin"
              className="font-semibold text-javanese transition hover:text-forest [text-underline-offset:3px]"
            >
              Login sebagai admin
            </Link>
          </p>
          {status ? <p className="mt-3 text-center text-[13px] text-red">{status}</p> : null}
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
