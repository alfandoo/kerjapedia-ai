"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { t, type TranslationKey } from "@/lib/translations";

import { type Language, type ResolvedLanguage } from "./language";

import { type Theme } from "./theme";

type SettingsContextType = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  language: "auto" | "id" | "en";
  setLanguage: (lang: "auto" | "id" | "en") => void;
  resolvedTheme: "dark" | "light";
  resolvedLanguage: "id" | "en";
  t: (key: TranslationKey) => string;
};

const SettingsContext = createContext<SettingsContextType>({
  theme: "system",
  setTheme: () => {},
  language: "auto",
  setLanguage: () => {},
  resolvedTheme: "light",
  resolvedLanguage: "id",
  t: (key) => key,
});

export function useSettings() {
  return useContext(SettingsContext);
}

function getSystemTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getSystemLanguage(): "id" | "en" {
  if (typeof window === "undefined") return "id";
  const lang = navigator.language.toLowerCase();
  return lang.startsWith("id") ? "id" : "en";
}

function applyDarkClass(resolved: "dark" | "light") {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.style.colorScheme = resolved;
  root.dataset.theme = resolved;
}

export function SettingsProvider({
  children,
  initialLanguage = "auto",
  initialResolvedLanguage = "id",
  initialTheme = "system",
}: {
  children: ReactNode;
  initialLanguage?: Language;
  initialResolvedLanguage?: ResolvedLanguage;
  initialTheme?: Theme;
}) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [language, setLanguageState] = useState<Language>(initialLanguage);
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">(
    initialTheme === "dark" ? "dark" : "light"
  );
  const [resolvedLanguage, setResolvedLanguage] =
    useState<ResolvedLanguage>(initialResolvedLanguage);

  const applyTheme = useCallback((t: Theme) => {
    const resolved = t === "system" ? getSystemTheme() : t;
    setResolvedTheme(resolved);
    applyDarkClass(resolved);
    document.cookie = `settings-theme=${t}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
  }, []);

  const applyLanguage = useCallback((lang: "auto" | "id" | "en") => {
    const resolved = lang === "auto" ? getSystemLanguage() : lang;
    setResolvedLanguage(resolved);
    document.documentElement.lang = resolved;
    // This non-sensitive preference lets the server render the chosen language.
    document.cookie = `settings-language=${lang}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
  }, []);

  const setTheme = useCallback(
    (t: Theme) => {
      setThemeState(t);
      applyTheme(t);
    },
    [applyTheme]
  );

  const setLanguage = useCallback(
    (lang: "auto" | "id" | "en") => {
      setLanguageState(lang);
      applyLanguage(lang);
    },
    [applyLanguage]
  );

  const translate = useCallback(
    (key: TranslationKey) => t(key, resolvedLanguage),
    [resolvedLanguage]
  );

  useLayoutEffect(() => {
    const savedTheme = initialTheme;
    const savedLang = initialLanguage;
    if (savedTheme) {
      // Hydrate persisted settings before synchronizing them to the document.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setThemeState(savedTheme);
      applyTheme(savedTheme);
    } else {
      applyTheme("system");
    }
    if (savedLang) {
      setLanguageState(savedLang);
      applyLanguage(savedLang);
    } else {
      applyLanguage("auto");
    }
  }, [applyTheme, applyLanguage, initialLanguage, initialTheme]);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (theme === "system") applyTheme("system");
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme, applyTheme]);

  return (
    <SettingsContext.Provider
      value={{
        theme,
        setTheme,
        language,
        setLanguage,
        resolvedTheme,
        resolvedLanguage,
        t: translate,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}
