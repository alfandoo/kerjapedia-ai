"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { login, register, googleLogin } from "@/features/auth";
import { useSettings } from "@/features/settings";
import type { UserSession } from "@/features/auth/types";

type AuthModalProps = {
  open: boolean;
  mode: "login" | "signup";
  onClose: () => void;
  onSuccess: (session: UserSession) => void;
};

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="size-[21px] fill-none stroke-current [stroke-linecap:round] [stroke-width:1.8]"
    >
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5">
      <path
        fill="currentColor"
        d="M17.1 12.7c0-2.5 2.1-3.8 2.2-3.9a4.6 4.6 0 0 0-3.6-2c-1.5-.2-3 .9-3.8.9-.8 0-2-.9-3.3-.9a4.9 4.9 0 0 0-4.1 2.5c-1.8 3-.5 7.5 1.2 10 .9 1.2 1.8 2.5 3.1 2.4 1.3-.1 1.8-.8 3.3-.8s2 .8 3.4.8 2.3-1.2 3.1-2.4a10.8 10.8 0 0 0 1.4-2.9 4.3 4.3 0 0 1-2.9-3.7ZM14.7 5.2a4.4 4.4 0 0 0 1-3.2 4.5 4.5 0 0 0-3 1.5 4.2 4.2 0 0 0-1.1 3.1 3.7 3.7 0 0 0 3.1-1.4Z"
      />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="size-5 fill-none stroke-current [stroke-linecap:round] [stroke-linejoin:round] [stroke-width:1.7]"
    >
      <path d="M6.7 3.8 9.2 8 7.6 9.6a14.4 14.4 0 0 0 6.8 6.8l1.6-1.6 4.2 2.5-.7 3.1c-.2.8-.9 1.4-1.8 1.4A15.5 15.5 0 0 1 2.2 6.3c0-.9.6-1.6 1.4-1.8l3.1-.7Z" />
    </svg>
  );
}

function EyeIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="size-5 fill-none stroke-current [stroke-linecap:round] [stroke-linejoin:round] [stroke-width:1.7]"
    >
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.8" />
      {hidden ? <path d="m4 4 16 16" /> : null}
    </svg>
  );
}

const providers = [
  { key: "apple", label: "Apple", icon: <AppleIcon /> },
  { key: "phone", label: "telepon", icon: <PhoneIcon /> },
];

export function AuthModal({ open, mode, onClose, onSuccess }: AuthModalProps) {
  const { t: translate, resolvedTheme, resolvedLanguage } = useSettings();
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const googleButtonRef = useRef<HTMLDivElement>(null);
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
  const [googleLoading, setGoogleLoading] = useState(false);
  const [gisReady, setGisReady] = useState(false);

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

  async function handleGoogleCredential(credential: string) {
    setError(null);
    setSubmitting(true);
    setGoogleLoading(true);
    try {
      const session = await googleLogin(credential);
      onSuccess(session);
      setStep("email");
      setEmail("");
      setName("");
      setPassword("");
      setPasswordVisible(false);
    } catch (reason) {
      setError((reason as Error).message || "Autentikasi Google gagal. Silakan coba kembali.");
    } finally {
      setSubmitting(false);
      setGoogleLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) {
      // State updates are part of opening the modal; this effect also manages GIS setup.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("Google sign-in belum dikonfigurasi.");
      return;
    }
    let cancelled = false;
    const googleClientId: string = clientId;
    // GIS button text follows the app language; theme follows the app theme.
    const gisLang = resolvedLanguage === "en" ? "en" : "id";
    const gisTheme: "outline" | "filled_black" =
      resolvedTheme === "dark" ? "filled_black" : "outline";
    const gisSrc = `https://accounts.google.com/gsi/client?hl=${gisLang}`;
    // Hide the GIS frame until the real button is drawn so its loading shimmer never shows.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGisReady(false);
    function renderGoogleButton() {
      const g = window.google;
      if (cancelled || !g?.accounts?.id || !googleButtonRef.current) return;
      g.accounts.id.initialize({
        client_id: googleClientId,
        callback: (response: { credential?: string }) => {
          if (response.credential) void handleGoogleCredential(response.credential);
          else setError("Autentikasi Google gagal.");
        },
      });
      googleButtonRef.current.innerHTML = "";
      g.accounts.id.renderButton(googleButtonRef.current, {
        type: "standard",
        theme: gisTheme,
        size: "large",
        width: 368,
        text: "continue_with",
        shape: "pill",
      });
      if (!cancelled) setGisReady(true);
    }
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src^="https://accounts.google.com/gsi/client"]'
    );
    if (existing && existing.src !== gisSrc) {
      // Reload GIS so the button text matches the newly selected language.
      existing.remove();
      try {
        delete (window as unknown as { google?: unknown }).google;
      } catch {
        /* ignore */
      }
    }
    if (window.google?.accounts?.id) {
      renderGoogleButton();
    } else {
      const script = document.createElement("script");
      script.src = gisSrc;
      script.async = true;
      script.onload = renderGoogleButton;
      script.onerror = () => {
        if (!cancelled) setError("Google sign-in belum dapat dimuat.");
      };
      document.head.appendChild(script);
    }
    return () => {
      cancelled = true;
    };
    // handleGoogleCredential is stable in practice (only calls setters/onSuccess);
    // re-run on open/theme/language so the GIS button matches the app.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resolvedLanguage, resolvedTheme]);

  useEffect(() => {
    if (!open) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") resetAndClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  });

  if (!open) return null;

  const labelClass = "mt-1 text-[13px] font-bold text-muted-text first:mt-0";
  const inputClass =
    "h-11 w-full rounded-xl border border-[#e5e5e5] bg-[#f7f7f8] px-4 text-sm text-tinta outline-none transition placeholder:text-[#676767] focus:border-javanese focus:ring-2 focus:ring-javanese/10";
  const submitClass =
    "min-h-[54px] w-full rounded-full bg-javanese text-sm font-bold text-white transition hover:bg-forest disabled:cursor-wait disabled:opacity-70";

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center p-5 max-[760px]:p-3 max-[760px]:pb-[max(12px,env(safe-area-inset-bottom))]">
      <button
        type="button"
        className="absolute inset-0 border-0 bg-[rgb(20_30_24/42%)] backdrop-blur-[2px]"
        aria-label="Tutup modal masuk"
        onClick={resetAndClose}
      />
      <div
        ref={dialogRef}
        className="relative w-[min(430px,100%)] max-h-[min(660px,calc(100svh-40px))] overflow-hidden rounded-[20px] border border-[#e5e5e5] bg-white shadow-[0_24px_70px_rgba(18,42,29,0.18)] max-[760px]:w-full max-[760px]:max-h-[calc(100svh_-_24px_-_env(safe-area-inset-bottom))] max-[760px]:rounded-[18px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onKeyDown={keepFocusInside}
      >
        <button
          type="button"
          className="absolute right-3 top-3 z-[2] grid size-11 place-items-center rounded-full border-0 bg-white text-[#0d0d0d] transition hover:bg-[#ececec]"
          aria-label="Tutup"
          disabled={submitting}
          onClick={resetAndClose}
        >
          <CloseIcon />
        </button>
        <div className="max-h-[min(660px,calc(100svh-40px))] overflow-y-auto px-8 pb-[30px] pt-[52px] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden max-[760px]:max-h-[calc(100svh_-_24px_-_env(safe-area-inset-bottom))] max-[760px]:px-[22px] max-[760px]:pb-[22px] max-[760px]:pt-[54px]">
          <header className="text-center">
            <h2
              id={titleId}
              className="font-display text-[30px] font-semibold leading-[1.15] tracking-[-0.025em] text-tinta max-[760px]:text-[27px]"
            >
              {mode === "signup" ? translate("auth.signupTitle") : translate("auth.loginTitle")}
            </h2>
            <p
              id={descriptionId}
              className="mx-auto mt-3.5 max-w-[320px] text-sm leading-[1.55] text-muted-text"
            >
              {translate("auth.subtitle")}
            </p>
          </header>

          <div className="mt-[34px] grid gap-2.5" aria-label="Pilihan masuk lainnya">
            <div className="relative grid min-h-[54px] place-items-center">
              <div
                ref={googleButtonRef}
                className={`flex w-full justify-center ${gisReady && !googleLoading ? "" : "invisible"}`}
                aria-hidden={!gisReady || googleLoading}
              />
              {!gisReady && !googleLoading ? (
                <div
                  className="absolute inset-0 grid place-items-center rounded-full border border-border bg-muted"
                  role="status"
                  aria-live="polite"
                  aria-label={translate("auth.checking")}
                >
                  <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    className="size-6 animate-spin fill-none stroke-javanese [stroke-width:2.5]"
                  >
                    <path d="M12 2a10 10 0 1 0 10 10" strokeLinecap="round" />
                  </svg>
                </div>
              ) : null}
              {googleLoading ? (
                <div
                  className="absolute inset-0 grid place-items-center"
                  role="status"
                  aria-live="polite"
                  aria-label={translate("auth.checkingAccount")}
                >
                  <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    className="size-6 animate-spin fill-none stroke-javanese [stroke-width:2.5]"
                  >
                    <path d="M12 2a10 10 0 1 0 10 10" strokeLinecap="round" />
                  </svg>
                </div>
              ) : null}
            </div>
            {providers
              .filter((provider) => provider.key !== "google")
              .map((provider) => (
              <button
                key={provider.key}
                type="button"
                disabled
                aria-disabled="true"
                className="grid min-h-[54px] grid-cols-[28px_minmax(0,1fr)_78px] items-center rounded-full border border-[#e5e5e5] bg-[#f7f7f8] px-[14px] text-sm font-semibold text-[#676767] transition disabled:cursor-not-allowed max-[760px]:grid-cols-[26px_minmax(0,1fr)_70px] max-[760px]:px-2.5 max-[760px]:text-xs"
              >
                <span className="grid size-[22px] place-items-center text-[#111713]">
                  {provider.icon}
                </span>
                <span className="justify-self-center">{provider.label}</span>
                <small className="text-[9px] font-bold uppercase tracking-[0.03em] text-[#758078] max-[760px]:text-[8px]">
                  {translate("auth.comingSoon")}
                </small>
              </button>
            ))}
          </div>

          <div
            className="my-[30px] grid grid-cols-[1fr_auto_1fr] items-center gap-[18px] text-[10px] font-bold text-[#676767] before:h-px before:bg-[#e5e5e5] before:content-[''] after:h-px after:bg-[#e5e5e5] after:content-['']"
            aria-hidden="true"
          >
            <span>{translate("auth.or")}</span>
          </div>

          <form className="grid gap-3" onSubmit={handleSubmit} noValidate>
            {step === "email" ? (
              <>
                {mode === "signup" ? (
                  <>
                    <label htmlFor="auth-modal-name" className={labelClass}>
                      {translate("auth.fullName")}
                    </label>
                    <input
                      ref={nameRef}
                      id="auth-modal-name"
                      name="name"
                      type="text"
                      autoComplete="name"
                      placeholder={translate("auth.fullName")}
                      value={name}
                      minLength={2}
                      required
                      onChange={(event) => setName(event.target.value)}
                      className={inputClass}
                    />
                  </>
                ) : null}
                <label htmlFor="auth-modal-email" className={labelClass}>
                  {translate("auth.email")}
                </label>
                <input
                  ref={emailRef}
                  id="auth-modal-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder={translate("auth.email")}
                  value={email}
                  required
                  onChange={(event) => setEmail(event.target.value)}
                  className={inputClass}
                />
                <button className={submitClass} type="submit">
                  {translate("auth.continue")}
                </button>
              </>
            ) : (
              <>
                <div className="flex min-h-[46px] items-center justify-between gap-3 border-l-[3px] border-javanese pl-[14px] pr-1 text-[13px] text-tinta">
                  <span className="truncate">{email}</span>
                  <button
                    type="button"
                    className="min-h-10 flex-none border-0 bg-transparent text-[11px] font-bold text-javanese transition hover:text-forest"
                    onClick={() => {
                      setStep("email");
                      setPassword("");
                      setPasswordVisible(false);
                      setError(null);
                    }}
                  >
                    {translate("auth.changeEmail")}
                  </button>
                </div>
                <label htmlFor="auth-modal-password" className={labelClass}>
                  {translate("auth.password")}
                </label>
                <div className="grid h-11 grid-cols-[minmax(0,1fr)_52px] overflow-hidden rounded-xl border border-[#e5e5e5] bg-[#f7f7f8] transition focus-within:border-javanese focus-within:ring-2 focus-within:ring-javanese/10">
                  <input
                    ref={passwordRef}
                    id="auth-modal-password"
                    name="password"
                    type={passwordVisible ? "text" : "password"}
                    autoComplete={mode === "signup" ? "new-password" : "current-password"}
                    placeholder={translate("auth.password")}
                    value={password}
                    minLength={mode === "signup" ? 8 : 1}
                    required
                    onChange={(event) => setPassword(event.target.value)}
                    className="min-w-0 border-0 bg-transparent px-4 text-sm text-tinta outline-none placeholder:text-[#676767]"
                  />
                  <button
                    type="button"
                    className="grid w-[52px] place-items-center border-0 bg-transparent text-[#526159] transition hover:text-tinta"
                    aria-label={
                      passwordVisible
                        ? translate("auth.hidePassword")
                        : translate("auth.showPassword")
                    }
                    aria-pressed={passwordVisible}
                    onClick={() => setPasswordVisible((visible) => !visible)}
                  >
                    <EyeIcon hidden={passwordVisible} />
                  </button>
                </div>
                <button className={submitClass} type="submit" disabled={submitting}>
                  {submitting
                    ? mode === "signup"
                      ? translate("auth.creating")
                      : translate("auth.checking")
                    : mode === "signup"
                      ? translate("auth.createAccount")
                      : translate("auth.login")}
                </button>
              </>
            )}
            <p
              className="min-h-[19px] text-center text-[11px] leading-[1.45] text-[#9b332b]"
              role="status"
              aria-live="polite"
            >
              {error
                ? `${mode === "signup" ? translate("auth.signup") : translate("auth.login")} ${translate("auth.failed")}: ${error}`
                : submitting
                  ? mode === "signup"
                    ? translate("auth.creatingAccount")
                    : translate("auth.checkingAccount")
                  : ""}
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
