"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "system" | "dark" | "light";

type SettingsContextType = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  language: "auto" | "id" | "en";
  setLanguage: (lang: "auto" | "id" | "en") => void;
};

const SettingsContext = createContext<SettingsContextType>({
  theme: "system",
  setTheme: () => {},
  language: "auto",
  setLanguage: () => {},
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
  const [theme, setTheme] = useState<Theme>("system");
  const [language, setLanguage] = useState<"auto" | "id" | "en">("auto");

  useEffect(() => {
    const savedTheme = localStorage.getItem("settings-theme") as Theme | null;
    const savedLang = localStorage.getItem("settings-language") as "auto" | "id" | "en" | null;
    if (savedTheme) setTheme(savedTheme);
    if (savedLang) setLanguage(savedLang);
  }, []);

  useEffect(() => {
    localStorage.setItem("settings-theme", theme);
    const resolved = theme === "system" ? getSystemTheme() : theme;
    document.documentElement.classList.toggle("dark", resolved === "dark");
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("settings-language", language);
    const resolved = language === "auto" ? getSystemLanguage() : language;
    document.documentElement.lang = resolved === "id" ? "id" : "en";
  }, [language]);

  return (
    <SettingsContext.Provider value={{ theme, setTheme, language, setLanguage }}>
      {children}
    </SettingsContext.Provider>
  );
}
