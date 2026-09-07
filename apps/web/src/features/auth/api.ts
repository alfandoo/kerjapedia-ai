import { API_URL, parseJsonResponse } from "@/lib/api-client";
import type { UserSession } from "./types";
import { clearStoredSession, getStoredSession, setStoredSession, loadStoredSession } from "./session";

let refreshInFlight: Promise<UserSession | null> | null = null;
const csrfHeaders = { "Content-Type": "application/json", "X-KerjaPedia-CSRF": "1" };
async function authenticate(action: string, input: object): Promise<UserSession | null> {
  // Finish initial cookie probing before a login can replace the session.
  await loadStoredSession();
  const response = await fetch(`${API_URL}/auth/${action}`, {
    method: "POST", credentials: "same-origin", headers: csrfHeaders, body: JSON.stringify(input),
  });
  if (response.status === 202) return null; // email confirmation required
  const session = await parseJsonResponse<UserSession>(response);
  setStoredSession(session);
  return session;
}
export async function login(email: string, password: string): Promise<UserSession> {
  const session = await authenticate("login", { email, password });
  if (!session) throw new Error("Periksa email Anda untuk kode verifikasi, lalu masuk kembali.");
  return session;
}
export async function register(
  name: string,
  email: string,
  password: string
): Promise<{ session: UserSession | null }> {
  const session = await authenticate("register", { name, email, password });
  return { session };
}
export async function googleLogin(idToken: string): Promise<UserSession> {
  const session = await authenticate("google", { id_token: idToken });
  if (!session) throw new Error("Autentikasi Google gagal.");
  return session;
}
export async function verifyEmailOtp(
  email: string,
  token: string
): Promise<UserSession> {
  const session = await authenticate("verify-email-otp", { email, token });
  if (!session) throw new Error("Kode verifikasi salah.");
  return session;
}
export async function resendEmailOtp(email: string): Promise<void> {
  await loadStoredSession();
  const response = await fetch(`${API_URL}/auth/resend-otp`, {
    method: "POST", credentials: "same-origin", headers: csrfHeaders, body: JSON.stringify({ email }),
  });
  if (!response.ok) throw new Error("Kode verifikasi belum dapat dikirim ulang.");
}
async function performSessionRefresh(): Promise<UserSession | null> {
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST", credentials: "same-origin", headers: csrfHeaders,
  });
  if (!response.ok) {
    if ([400, 401, 403].includes(response.status)) clearStoredSession();
    return null;
  }
  const session = await response.json() as UserSession;
  setStoredSession(session);
  return session;
}
function refreshStoredSession(): Promise<UserSession | null> {
  if (!refreshInFlight) refreshInFlight = performSessionRefresh().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}
export async function fetchWithAuthRetry(url: string, options: RequestInit, signal?: AbortSignal): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.delete("Authorization");
  if (!["GET", "HEAD"].includes((options.method ?? "GET").toUpperCase())) headers.set("X-KerjaPedia-CSRF", "1");
  const init = { ...options, headers, signal, credentials: "same-origin" as const };
  const response = await fetch(url, init);
  if (response.status !== 401) return response;
  const fresh = await refreshStoredSession();
  return fresh ? fetch(url, init) : response;
}
export async function signOut(): Promise<void> {
  await loadStoredSession();
  if (refreshInFlight) await refreshInFlight;
  try {
    const response = await fetchWithAuthRetry(`${API_URL}/auth/logout`, { method: "POST" });
    if (!response.ok) throw new Error("Logout failed");
  } catch {
    throw new Error("Sesi server belum berhasil dicabut. Silakan coba keluar lagi.");
  }
  clearStoredSession();
}
export { clearStoredSession, getStoredSession } from "./session";

export async function updateProfile(name: string): Promise<void> {
  const owner = getStoredSession()?.user.user_id;
  if (!owner) throw new Error("No active session");
  const response = await fetchWithAuthRetry(`${API_URL}/auth/profile`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  });
  const next = await parseJsonResponse<UserSession>(response);
  if (getStoredSession()?.user.user_id !== owner) throw new Error("Session changed");
  setStoredSession(next);
}
export async function deleteAccount(): Promise<void> {
  const owner = getStoredSession()?.user.user_id;
  if (!owner) throw new Error("No active session");
  const response = await fetchWithAuthRetry(`${API_URL}/auth/account`, { method: "DELETE" });
  await parseJsonResponse<{ status: string }>(response);
  clearStoredSession();
}
