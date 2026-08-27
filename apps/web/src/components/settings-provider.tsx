"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { t, type TranslationKey } from "@/lib/translations";

type Theme = "system" | "dark" | "light";

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
  const body = document.body;
  if (resolved === "dark") {
    root.classList.add("dark");
    root.classList.remove("light");
    body.style.backgroundColor = "#000000";
    body.style.color = "#f3f4f6";
  } else {
    root.classList.remove("dark");
    root.classList.add("light");
    body.style.backgroundColor = "";
    body.style.color = "";
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [language, setLanguageState] = useState<"auto" | "id" | "en">("auto");
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("light");
  const [resolvedLanguage, setResolvedLanguage] = useState<"id" | "en">("id");

  const applyTheme = useCallback((t: Theme) => {
    const resolved = t === "system" ? getSystemTheme() : t;
    setResolvedTheme(resolved);
    applyDarkClass(resolved);
  }, []);

  const applyLanguage = useCallback((lang: "auto" | "id" | "en") => {
    const resolved = lang === "auto" ? getSystemLanguage() : lang;
    setResolvedLanguage(resolved);
    document.documentElement.lang = resolved;
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("settings-theme", t);
    applyTheme(t);
  }, [applyTheme]);

  const setLanguage = useCallback((lang: "auto" | "id" | "en") => {
    setLanguageState(lang);
    localStorage.setItem("settings-language", lang);
    applyLanguage(lang);
  }, [applyLanguage]);

  const translate = useCallback((key: TranslationKey) => t(key, resolvedLanguage), [resolvedLanguage]);

  useEffect(() => {
    const savedTheme = localStorage.getItem("settings-theme") as Theme | null;
    const savedLang = localStorage.getItem("settings-language") as "auto" | "id" | "en" | null;
    if (savedTheme) {
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
  }, [applyTheme, applyLanguage]);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (theme === "system") applyTheme("system");
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme, applyTheme]);

  return (
    <SettingsContext.Provider value={{ theme, setTheme, language, setLanguage, resolvedTheme, resolvedLanguage, t: translate }}>
      {children}
    </SettingsContext.Provider>
  );
}
