"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { SourcePanel } from "@/components/source-panel";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("secret");
  const [status, setStatus] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Memeriksa sesi...");
    try {
      const session = await login(email, password);
      window.localStorage.setItem("kerjapedia-session", JSON.stringify(session));
      window.dispatchEvent(new Event("kerjapedia-session-change"));
      setStatus(`Login berhasil sebagai ${session.user.name}.`);
      router.push(session.user.roles.includes("admin") ? "/admin" : "/");
    } catch (err) {
      setStatus(`Login gagal: ${(err as Error).message}`);
    }
  }

  return (
    <AppShell rightPanel={<SourcePanel />}>
      <section className="auth-page">
        <div className="page-heading">
          <h1>Login</h1>
          <p>Masuk untuk menyimpan riwayat percakapan dan mengakses fitur admin jika berwenang.</p>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button className="send-button" type="submit">
            Masuk
          </button>
          {status ? <p className="form-status">{status}</p> : null}
        </form>
      </section>
    </AppShell>
  );
}
