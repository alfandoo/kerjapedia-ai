"use client";

import { ArrowRight, Eye, EyeOff } from "lucide-react";
import styles from "@/features/admin/components/admin-access.module.css";
import { ScaleIcon } from "@/components/icons";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { login } from "@/features/auth/api";

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
      router.push("/admin/dashboard");
    } catch (err) {
      const message = (err as Error).message;
      setStatus(message || "Gagal. Coba lagi.");
      setLoading(false);
    }
  }

  return (
    <main className={`${styles.screen} ${styles.loginScreen}`}>
      <div className={styles.content}>
        <div className={styles.brand}>
          <ScaleIcon className="size-5" aria-hidden="true" />
          <span>KerjaPedia AI</span>
        </div>
        <div className={styles.panel}>
          <p className={styles.eyebrow}>Konsol admin</p>
          <h1 className={styles.title}>Masuk sebagai admin</h1>
          <p className={styles.description}>
            Gunakan akun admin untuk mengelola dokumen dan pengaturan KerjaPedia AI.
          </p>
          <form className={styles.form} onSubmit={handleSubmit} aria-busy={loading}>
            <div className={styles.field}>
              <label htmlFor="email">Email</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                disabled={loading}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={styles.input}
              />
            </div>
            <div className={styles.field}>
              <label htmlFor="password">Kata sandi</label>
              <div className={styles.passwordField}>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  disabled={loading}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={styles.input}
                />
                <button
                  type="button"
                  className={styles.reveal}
                  aria-label={showPassword ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                  aria-pressed={showPassword}
                  aria-controls="password"
                  onClick={() => setShowPassword((prev) => !prev)}
                >
                  {showPassword ? (
                    <EyeOff size={18} aria-hidden="true" />
                  ) : (
                    <Eye size={18} aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>
            {status ? (
              <p role="alert" className={styles.error}>
                {status}
              </p>
            ) : null}
            <button className={styles.primary} type="submit" disabled={loading}>
              <span role="status">{loading ? "Memeriksa akun..." : "Masuk"}</span>
              {!loading ? <ArrowRight size={18} aria-hidden="true" /> : null}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
