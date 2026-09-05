export type Language = "auto" | "id" | "en";
export type ResolvedLanguage = "id" | "en";

export function parseLanguage(value: string | null | undefined): Language | null {
  return value === "auto" || value === "id" || value === "en" ? value : null;
}

export function resolveLanguage(language: Language, browserLanguage: string): ResolvedLanguage {
  return language === "auto"
    ? browserLanguage.toLowerCase().startsWith("id")
      ? "id"
      : "en"
    : language;
}
