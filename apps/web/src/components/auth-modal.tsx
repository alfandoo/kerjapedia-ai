"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { login, register, SESSION_STORAGE_KEY } from "@/lib/api";
import type { UserSession } from "@/lib/types";

type AuthModalProps = {
  open: boolean;
  mode: "login" | "signup";
  onClose: () => void;
  onSuccess: (session: UserSession) => void;
};

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.9h5.4a4.7 4.7 0 0 1-2 3v2.6h3.3c1.9-1.8 2.9-4.4 2.9-7.5Z"
      />
      <path
        fill="#34A853"
        d="M12 22c2.7 0 5-.9 6.7-2.3l-3.3-2.6c-.9.6-2.1 1-3.4 1a5.9 5.9 0 0 1-5.5-4.1H3.1v2.7A10 10 0 0 0 12 22Z"
      />
      <path fill="#FBBC05" d="M6.5 14a6 6 0 0 1 0-3.9V7.4H3.1a10 10 0 0 0 0 9.3L6.5 14Z" />
      <path
        fill="#EA4335"
        d="M12 6c1.6 0 3 .5 4.2 1.6l3.1-3A10.4 10.4 0 0 0 3.1 7.4l3.4 2.7A5.9 5.9 0 0 1 12 6Z"
      />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M17.1 12.7c0-2.5 2.1-3.8 2.2-3.9a4.6 4.6 0 0 0-3.6-2c-1.5-.2-3 .9-3.8.9-.8 0-2-.9-3.3-.9a4.9 4.9 0 0 0-4.1 2.5c-1.8 3-.5 7.5 1.2 10 .9 1.2 1.8 2.5 3.1 2.4 1.3-.1 1.8-.8 3.3-.8s2 .8 3.4.8 2.3-1.2 3.1-2.4a10.8 10.8 0 0 0 1.4-2.9 4.3 4.3 0 0 1-2.9-3.7ZM14.7 5.2a4.4 4.4 0 0 0 1-3.2 4.5 4.5 0 0 0-3 1.5 4.2 4.2 0 0 0-1.1 3.1 3.7 3.7 0 0 0 3.1-1.4Z"
      />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6.7 3.8 9.2 8 7.6 9.6a14.4 14.4 0 0 0 6.8 6.8l1.6-1.6 4.2 2.5-.7 3.1c-.2.8-.9 1.4-1.8 1.4A15.5 15.5 0 0 1 2.2 6.3c0-.9.6-1.6 1.4-1.8l3.1-.7Z" />
    </svg>
  );
}

function EyeIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.8" />
      {hidden ? <path d="m4 4 16 16" /> : null}
    </svg>
  );
}

const providers = [
  { label: "Google", icon: <GoogleIcon /> },
  { label: "Apple", icon: <AppleIcon /> },
  { label: "telepon", icon: <PhoneIcon /> },
];

export function AuthModal({ open, mode, onClose, onSuccess }: AuthModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<"email" | "password">("email");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => (mode === "signup" ? nameRef.current : emailRef.current)?.focus(), 0);
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mode, open]);

  useEffect(() => {
    if (open && step === "password") {
      window.setTimeout(() => passwordRef.current?.focus(), 0);
    }
  }, [open, step]);

  function resetAndClose() {
    if (submitting) return;
    setStep("email");
    setEmail("");
    setName("");
    setPassword("");
    setPasswordVisible(false);
    setError(null);
    onClose();
  }

  function keepFocusInside(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (step === "email") {
      if (!event.currentTarget.checkValidity()) {
        event.currentTarget.reportValidity();
        return;
      }
      setStep("password");
      return;
    }

    if (!password) {
      passwordRef.current?.reportValidity();
      return;
    }

    if (mode === "signup" && password.length < 8) {
      setError("Password minimal 8 karakter.");
      return;
    }

    setSubmitting(true);
    try {
      const session =
        mode === "signup"
          ? await register(name.trim(), email.trim(), password)
          : await login(email.trim(), password);
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
      window.dispatchEvent(new Event("kerjapedia-session-change"));
      onSuccess(session);
      setStep("email");
      setEmail("");
      setName("");
      setPassword("");
      setPasswordVisible(false);
    } catch (reason) {
      setError((reason as Error).message || "Autentikasi gagal. Silakan coba kembali.");
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") resetAndClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  });

  if (!open) return null;

  return (
    <div className="auth-modal-layer">
      <button
        type="button"
        className="auth-modal-backdrop"
        aria-label="Tutup modal masuk"
        onClick={resetAndClose}
      />
      <div
        ref={dialogRef}
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onKeyDown={keepFocusInside}
      >
        <button
          type="button"
          className="auth-modal-close"
          aria-label="Tutup"
          disabled={submitting}
          onClick={resetAndClose}
        >
          <CloseIcon />
        </button>
        <div className="auth-modal-scroll">
          <header className="auth-modal-heading">
            <h2 id={titleId}>
              {mode === "signup" ? "Buat akun KerjaPedia" : "Masuk ke KerjaPedia"}
            </h2>
            <p id={descriptionId}>
              Dapatkan jawaban yang lebih personal dan simpan riwayat percakapan Anda.
            </p>
          </header>

          <div className="auth-provider-list" aria-label="Pilihan masuk lainnya">
            {providers.map((provider) => (
              <button key={provider.label} type="button" disabled aria-disabled="true">
                <span className="auth-provider-icon">{provider.icon}</span>
                <span className="auth-provider-label">Lanjutkan dengan {provider.label}</span>
                <small>Segera hadir</small>
              </button>
            ))}
          </div>

          <div className="auth-divider" aria-hidden="true">
            <span>ATAU</span>
          </div>

          <form className="auth-modal-form" onSubmit={handleSubmit} noValidate>
            {step === "email" ? (
              <>
                {mode === "signup" ? (
                  <>
                    <label htmlFor="auth-modal-name">Nama lengkap</label>
                    <input
                      ref={nameRef}
                      id="auth-modal-name"
                      name="name"
                      type="text"
                      autoComplete="name"
                      placeholder="Nama lengkap"
                      value={name}
                      minLength={2}
                      required
                      onChange={(event) => setName(event.target.value)}
                    />
                  </>
                ) : null}
                <label htmlFor="auth-modal-email">Alamat email</label>
                <input
                  ref={emailRef}
                  id="auth-modal-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="Alamat email"
                  value={email}
                  required
                  onChange={(event) => setEmail(event.target.value)}
                />
                <button className="auth-modal-submit" type="submit">
                  Lanjutkan
                </button>
              </>
            ) : (
              <>
                <div className="auth-selected-email">
                  <span>{email}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setStep("email");
                      setPassword("");
                      setPasswordVisible(false);
                      setError(null);
                    }}
                  >
                    Ganti email
                  </button>
                </div>
                <label htmlFor="auth-modal-password">Password</label>
                <div className="auth-password-field">
                  <input
                    ref={passwordRef}
                    id="auth-modal-password"
                    name="password"
                    type={passwordVisible ? "text" : "password"}
                    autoComplete={mode === "signup" ? "new-password" : "current-password"}
                    placeholder="Password"
                    value={password}
                    minLength={mode === "signup" ? 8 : 1}
                    required
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    type="button"
                    aria-label={passwordVisible ? "Sembunyikan password" : "Tampilkan password"}
                    aria-pressed={passwordVisible}
                    onClick={() => setPasswordVisible((visible) => !visible)}
                  >
                    <EyeIcon hidden={passwordVisible} />
                  </button>
                </div>
                <button className="auth-modal-submit" type="submit" disabled={submitting}>
                  {submitting
                    ? mode === "signup"
                      ? "Membuat akun..."
                      : "Memeriksa..."
                    : mode === "signup"
                      ? "Buat akun"
                      : "Masuk"}
                </button>
              </>
            )}
            <p className="auth-modal-status" role="status" aria-live="polite">
              {error
                ? `${mode === "signup" ? "Pendaftaran" : "Login"} gagal: ${error}`
                : submitting
                  ? mode === "signup"
                    ? "Membuat akun Anda..."
                    : "Memeriksa akun Anda..."
                  : ""}
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
