import id from "./id";
import en from "./en";

export type TranslationKey = keyof typeof id;

export const translations = { id, en } as const;

export function t(key: TranslationKey, lang: "id" | "en"): string {
  return translations[lang]?.[key] ?? translations.id[key] ?? key;
}
