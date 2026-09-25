"use client";

import { ArrowLeft, Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import styles from "@/features/admin/components/admin-access.module.css";
import { ScaleIcon } from "@/components/icons";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { login, signOut } from "@/features/auth/api";

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
        // Revoke the just-issued HttpOnly session so a non-admin credential
        // never leaves an authenticated cookie behind.
        try {
          await signOut();
        } catch {
          /* BFF already cleared cookies on failure; keep the denial message. */
        }
        setStatus("Akses ditolak. Hanya admin yang dapat masuk.");
        setLoading(false);
        return;
      }
      router.push("/admin/dashboard");
    } catch (err) {
      const message = (err as Error).message;
      setStatus(message || "Gagal masuk. Coba lagi.");
      setLoading(false);
    }
  }

  return (
    <main className={`${styles.screen} ${styles.loginScreen}`}>
      <div className={styles.content}>
        <section className={styles.context} aria-label="Tentang konsol admin">
          <Image
            src="/images/admin-legal-library.png"
            alt=""
            fill
            priority
            sizes="(max-width: 780px) 100vw, 46vw"
            className={styles.contextImage}
          />
          <div className={styles.contextOverlay} aria-hidden="true" />
          <div className={styles.contextBrand}>
            <ScaleIcon className="size-5" aria-hidden="true" />
            <span>KerjaPedia AI</span>
          </div>
          <div className={styles.contextCopy}>
            <p className={styles.contextLabel}>Ruang pengelolaan</p>
            <p className={styles.contextTitle}>Pengetahuan hukum, terjaga.</p>
            <p className={styles.contextDescription}>
              Kelola dokumen dan pengaturan dari satu ruang kerja.
            </p>
          </div>
        </section>

        <section className={styles.loginArea} aria-labelledby="login-title">
          <Link href="/chat" className={styles.backLink}>
            <ArrowLeft size={18} aria-hidden="true" />
            Kembali ke chat
          </Link>
          <div className={styles.panel}>
            <p className={styles.eyebrow}>Akses administrator</p>
            <h1 id="login-title" className={styles.title}>
              Masuk sebagai admin
            </h1>
            <p className={styles.description}>
              Gunakan akun admin untuk mengelola dokumen dan pengaturan KerjaPedia AI.
            </p>
            <form className={styles.form} onSubmit={handleSubmit} aria-busy={loading}>
              <div className={styles.field}>
                <label htmlFor="email">Email</label>
                <div className={styles.inputWithIcon}>
                  <Mail className={styles.fieldIcon} size={18} aria-hidden="true" />
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
              </div>
              <div className={styles.field}>
                <label htmlFor="password">Kata sandi</label>
                <div className={styles.passwordField}>
                  <LockKeyhole className={styles.fieldIcon} size={18} aria-hidden="true" />
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
                    disabled={loading}
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
                <span role="status" className="inline-flex items-center gap-2">
                  {loading ? (
                    <svg
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                      className="size-4 animate-spin fill-none stroke-current [stroke-width:2.5]"
                    >
                      <path d="M12 2a10 10 0 1 0 10 10" strokeLinecap="round" />
                    </svg>
                  ) : null}
                  {loading ? "Memeriksa akun..." : "Masuk"}
                </span>
              </button>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}
