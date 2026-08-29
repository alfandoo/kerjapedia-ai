import { API_URL, parseJsonResponse } from "@/lib/api-client";
import type { UserSession } from "./types";
import { clearStoredSession, getStoredSession, SESSION_STORAGE_KEY } from "./session";

export async function login(email: string, password: string): Promise<UserSession> {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJsonResponse<UserSession>(response);
}

export async function register(
  name: string,
  email: string,
  password: string
): Promise<UserSession> {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  return parseJsonResponse<UserSession>(response);
}

async function refreshStoredSession(): Promise<UserSession | null> {
  const session = getStoredSession();
  if (!session?.refresh_token) return null;
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  if (!response.ok) return null;
  const fresh = await response.json();
  if (!fresh.access_token) return null;
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(fresh));
  window.dispatchEvent(new Event("kerjapedia-session-change"));
  return fresh as UserSession;
}

export async function fetchWithAuthRetry(
  url: string,
  options: RequestInit,
  signal?: AbortSignal
): Promise<Response> {
  const response = await fetch(url, { ...options, signal });
  if (response.status !== 401) return response;
  const fresh = await refreshStoredSession();
  if (!fresh) return response;
  return fetch(url, {
    ...options,
    signal,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${fresh.access_token}`,
    },
  });
}

export async function signOut(): Promise<void> {
  const session = getStoredSession();
  if (!session) return;
  try {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
  } catch {
    // Local cleanup below still runs when the API is unreachable.
  }
  clearStoredSession();
}

export { clearStoredSession, getStoredSession, SESSION_STORAGE_KEY } from "./session";
