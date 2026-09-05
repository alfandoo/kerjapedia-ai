export function readPreference(name: string): string | null {
  if (typeof document === "undefined") return null;
  try {
    const value = document.cookie.split("; ").find(item => item.startsWith(`${name}=`));
    return value ? decodeURIComponent(value.slice(name.length + 1)) : null;
  } catch { return null; }
}
export function writePreference(name: string, value: string): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
}
