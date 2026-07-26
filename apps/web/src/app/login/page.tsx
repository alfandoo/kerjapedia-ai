"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { login, register, SESSION_STORAGE_KEY } from "@/lib/api";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSignup = searchParams.get("mode") === "signup";
  const [name, setName] = useState("");
  const [email, setEmail] = useState(isSignup ? "" : "admin@example.com");
  const [password, setPassword] = useState(isSignup ? "" : "secret");
  const [status, setStatus] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Memeriksa sesi...");
    try {
      const session = isSignup
        ? await register(name.trim(), email.trim(), password)
        : await login(email.trim(), password);
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
      window.dispatchEvent(new Event("kerjapedia-session-change"));
      setStatus(
        isSignup
          ? `Akun siap digunakan sebagai ${session.user.name}.`
          : `Login berhasil sebagai ${session.user.name}.`
      );
      router.push(!isSignup && session.user.roles.includes("admin") ? "/admin" : "/");
    } catch (err) {
      setStatus(`Login gagal: ${(err as Error).message}`);
    }
  }

  return (
    <AppShell>
      <section className="auth-page">
        <div className="page-heading">
          <h1>{isSignup ? "Daftar gratis" : "Masuk"}</h1>
          <p>
            {isSignup
              ? "Buat sesi KerjaPedia agar percakapan dan riwayat Anda tetap tersedia."
              : "Masuk untuk menyimpan riwayat percakapan dan mengakses fitur sesuai kewenangan."}
          </p>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          {isSignup ? (
            <>
              <label htmlFor="name">Nama lengkap</label>
              <input
                id="name"
                type="text"
                autoComplete="name"
                minLength={2}
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </>
          ) : null}
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
          <input
            id="password"
            type="password"
            autoComplete={isSignup ? "new-password" : "current-password"}
            minLength={isSignup ? 8 : 1}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button className="send-button" type="submit">
            {isSignup ? "Buat akun" : "Masuk"}
          </button>
          <p className="auth-mode-switch">
            {isSignup ? "Sudah memiliki akun?" : "Belum memiliki akun?"}{" "}
            <Link href={isSignup ? "/login" : "/login?mode=signup"}>
              {isSignup ? "Masuk" : "Daftar gratis"}
            </Link>
          </p>
          {status ? <p className="form-status">{status}</p> : null}
        </form>
      </section>
    </AppShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageContent />
    </Suspense>
  );
}
