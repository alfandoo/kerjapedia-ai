"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useSettings } from "@/features/settings";

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
};

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const { theme, setTheme, language, setLanguage, t: translate } = useSettings();
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [languageOpen, setLanguageOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    // State resets are part of opening the modal, while this effect also manages focus and scroll lock.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAppearanceOpen(false);
    setLanguageOpen(false);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [onClose, open]);

  if (!open) return null;

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
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

  const themeLabel =
    theme === "system"
      ? translate("settings.system")
      : theme === "dark"
        ? translate("settings.dark")
        : translate("settings.light");
  const langLabel =
    language === "auto"
      ? translate("settings.auto")
      : language === "id"
        ? translate("settings.indonesian")
        : translate("settings.english");

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center">
      <button
        type="button"
        className="absolute inset-0 w-full border-0 bg-[rgba(10,28,25,0.5)]"
        aria-label={translate("settings.close")}
        onClick={onClose}
      />
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onKeyDown={keepFocusInside}
        className="relative z-[1] flex w-full max-w-[420px] max-h-[70vh] overflow-y-auto rounded-2xl bg-white shadow-2xl [scrollbar-width:none] [&::-webkit-scrollbar]:hidden max-[760px]:mx-4"
      >
        <div className="flex w-full flex-col">
          <header className="flex items-center gap-3 border-b border-[#e5e5e5] px-4 py-3">
            <h2
              id="settings-title"
              className="flex-1 text-center text-[15px] font-semibold text-tinta"
            >
              {translate("settings.title")}
            </h2>
          </header>

          <div className="flex-1 p-5">
            <div className="space-y-5">
              <p className="text-[13px] font-medium text-muted-text">
                {translate("settings.general")}
              </p>
              <div className="rounded-2xl border border-[#e5e5e5] bg-[#f7f7f8]">
                <button
                  type="button"
                  className={`flex min-h-[60px] w-full items-center gap-4 px-4 text-left transition hover:bg-[#ececec] ${
                    appearanceOpen ? "rounded-t-2xl border-2 border-javanese" : "rounded-t-2xl"
                  }`}
                  onClick={() => {
                    setAppearanceOpen(!appearanceOpen);
                    setLanguageOpen(false);
                  }}
                >
                  <span className="flex size-5 shrink-0 items-center justify-center text-muted-text">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="size-5"
                    >
                      <circle cx="12" cy="12" r="5" />
                      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                    </svg>
                  </span>
                  <div className="flex-1">
                    <span className="block text-[15px] font-medium text-tinta">
                      {translate("settings.appearance")}
                    </span>
                    <span className="block text-[13px] text-muted-text">{themeLabel}</span>
                  </div>
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`size-4 text-[#676767] transition-transform ${appearanceOpen ? "rotate-180" : ""}`}
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </button>
                {appearanceOpen ? (
                  <div className="border-t border-[#e5e5e5] bg-white">
                    {[
                      { value: "system" as const, label: translate("settings.system") },
                      { value: "dark" as const, label: translate("settings.dark") },
                      { value: "light" as const, label: translate("settings.light") },
                    ].map((option, index) => (
                      <button
                        key={option.value}
                        type="button"
                        className={`flex min-h-[44px] w-full items-center px-4 text-left text-[13px] transition hover:bg-[#ececec] ${
                          index === 2 ? "rounded-b-2xl" : ""
                        } ${theme === option.value ? "font-semibold text-tinta bg-[#ececec]" : "text-muted-text"}`}
                        onClick={() => {
                          setTheme(option.value);
                          // State resets are part of opening the modal, while this effect also manages focus and scroll lock.
                          // eslint-disable-next-line react-hooks/set-state-in-effect
                          setAppearanceOpen(false);
                        }}
                      >
                        <span className="flex-1">{option.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="border-t border-[#e5e5e5]" />
                <button
                  type="button"
                  className={`flex min-h-[60px] w-full items-center gap-4 px-4 text-left transition hover:bg-[#ececec] ${
                    languageOpen ? "" : "rounded-b-2xl"
                  }`}
                  onClick={() => {
                    setLanguageOpen(!languageOpen);
                    // State resets are part of opening the modal, while this effect also manages focus and scroll lock.
                    // eslint-disable-next-line react-hooks/set-state-in-effect
                    setAppearanceOpen(false);
                  }}
                >
                  <span className="flex size-5 shrink-0 items-center justify-center text-muted-text">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="size-5"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    </svg>
                  </span>
                  <div className="flex-1">
                    <span className="block text-[15px] font-medium text-tinta">
                      {translate("settings.language")}
                    </span>
                    <span className="block text-[13px] text-muted-text">{langLabel}</span>
                  </div>
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`size-4 text-[#676767] transition-transform ${languageOpen ? "rotate-180" : ""}`}
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </button>
                {languageOpen ? (
                  <div className="border-t border-[#e5e5e5] bg-white">
                    {[
                      { value: "auto" as const, label: translate("settings.auto") },
                      { value: "id" as const, label: translate("settings.indonesian") },
                      { value: "en" as const, label: translate("settings.english") },
                    ].map((option, index) => (
                      <button
                        key={option.value}
                        type="button"
                        className={`flex min-h-[44px] w-full items-center px-4 text-left text-[13px] transition hover:bg-[#ececec] rounded-b-2xl ${
                          language === option.value
                            ? "font-semibold text-tinta bg-[#ececec]"
                            : "text-muted-text"
                        }`}
                        onClick={() => {
                          setLanguage(option.value);
                          setLanguageOpen(false);
                        }}
                      >
                        <span className="flex-1">{option.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-[#e5e5e5] bg-[#f7f7f8]">
                <button
                  type="button"
                  className="flex min-h-[60px] w-full items-center gap-4 px-4 text-left transition hover:bg-[#ececec] rounded-2xl"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center text-muted-text">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="size-5"
                    >
                      <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />
                    </svg>
                  </span>
                  <span className="flex-1 text-[15px] font-medium text-tinta">
                    {translate("settings.dataControl")}
                  </span>
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="size-4 text-[#676767]"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
