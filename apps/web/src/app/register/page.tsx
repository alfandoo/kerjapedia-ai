"use client";

import Link from "next/link";
import { ScaleIcon } from "@/components/icons";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { login, register } from "@/features/auth/api";
import { translateAuthError } from "@/features/auth/error-messages";
import { useSettings } from "@/features/settings";

function RegisterPageContent() {
  const router = useRouter();
  const { t: translate } = useSettings();
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
      if (isSignup) {
        const { session } = await register(name.trim(), email.trim(), password);
        if (!session) {
          setStatus("Periksa email Anda untuk kode verifikasi, lalu selesaikan pendaftaran.");
          return;
        }
      } else {
        await login(email.trim(), password);
      }
      router.push("/chat");
    } catch (err) {
      setStatus(translateAuthError(translate, (err as Error).message || "Gagal. Coba lagi."));
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background bg-[radial-gradient(circle_at_50%_0,#f4fbfa_0,#fff_32rem)] p-4 sm:p-6 dark:bg-none">
      <div className="w-full max-w-[400px] rounded-2xl border border-[#e5e5e5] bg-white p-6 shadow-[0_16px_40px_rgba(21,32,31,0.08)] sm:p-[44px_36px_36px]">
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
                className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 text-sm text-tinta transition focus:border-javanese focus:ring-2 focus:ring-javanese/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
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
            className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 text-sm text-tinta transition focus:border-javanese focus:ring-2 focus:ring-javanese/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
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
              className="h-[46px] w-full rounded-[10px] border border-[#e5e5e5] bg-[#f7f7f8] px-3.5 pr-11 text-sm text-tinta transition focus:border-javanese focus:ring-2 focus:ring-javanese/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md px-3 text-tinta transition hover:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
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
            className="mt-5 h-[46px] w-full rounded-[10px] bg-javanese px-5 text-sm font-semibold text-white transition hover:bg-forest focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese disabled:pointer-events-none disabled:opacity-60"
            type="submit"
            disabled={loading}
          >
            {loading ? "Memproses..." : isSignup ? "Buat akun" : "Masuk"}
          </button>
          <p className="mt-3 flex items-center justify-center gap-1 text-center text-xs text-muted-text">
            {isSignup ? "Sudah punya akun? " : "Belum punya akun? "}
            <Link
              href={isSignup ? "/register" : "/register?mode=signup"}
              className="inline-flex min-h-[44px] items-center rounded px-1 font-semibold text-javanese transition hover:text-forest hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese [text-underline-offset:3px]"
            >
              {isSignup ? "Masuk" : "Daftar gratis"}
            </Link>
          </p>
          <p className="mt-1 text-center text-xs text-muted-text">
            <Link
              href="/login-admin"
              className="inline-flex min-h-[44px] items-center justify-center rounded px-2 font-semibold text-javanese transition hover:text-forest hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese [text-underline-offset:3px]"
            >
              Login sebagai admin
            </Link>
          </p>
          {status ? (
            <p
              role="alert"
              className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/30 px-3 py-2.5 text-left text-[12px] leading-[1.5] text-destructive"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="mt-[1px] size-4 shrink-0 fill-none stroke-current [stroke-linecap:round] [stroke-linejoin:round] [stroke-width:1.8]"
              >
                <path d="M10.3 4 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0Z" />
                <path d="M12 9v4M12 17h.01" />
              </svg>
              <span>{status}</span>
            </p>
          ) : null}
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
