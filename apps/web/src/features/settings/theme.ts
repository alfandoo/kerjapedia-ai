export type Theme = "system" | "dark" | "light";

export function parseTheme(value: string | null | undefined): Theme | null {
  return value === "system" || value === "dark" || value === "light" ? value : null;
}
