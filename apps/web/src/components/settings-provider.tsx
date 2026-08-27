"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "system" | "dark" | "light";

type SettingsContextType = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  language: "auto" | "id" | "en";
  setLanguage: (lang: "auto" | "id" | "en") => void;
  resolvedTheme: "dark" | "light";
};

const SettingsContext = createContext<SettingsContextType>({
  theme: "system",
  setTheme: () => {},
  language: "auto",
  setLanguage: () => {},
  resolvedTheme: "light",
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

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [language, setLanguage] = useState<"auto" | "id" | "en">("auto");
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("light");

  const applyTheme = useCallback((t: Theme) => {
    const resolved = t === "system" ? getSystemTheme() : t;
    setResolvedTheme(resolved);
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark");
    root.style.colorScheme = resolved;
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("settings-theme", t);
    applyTheme(t);
  }, [applyTheme]);

  useEffect(() => {
    const savedTheme = localStorage.getItem("settings-theme") as Theme | null;
    const savedLang = localStorage.getItem("settings-language") as "auto" | "id" | "en" | null;
    if (savedTheme) {
      setThemeState(savedTheme);
      applyTheme(savedTheme);
    } else {
      applyTheme("system");
    }
    if (savedLang) setLanguage(savedLang);
  }, [applyTheme]);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (theme === "system") applyTheme("system");
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme, applyTheme]);

  useEffect(() => {
    localStorage.setItem("settings-language", language);
    const resolved = language === "auto" ? getSystemLanguage() : language;
    document.documentElement.lang = resolved === "id" ? "id" : "en";
  }, [language]);

  return (
    <SettingsContext.Provider value={{ theme, setTheme, language, setLanguage, resolvedTheme }}>
      {children}
    </SettingsContext.Provider>
  );
}
