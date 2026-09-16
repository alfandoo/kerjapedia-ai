"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { UserSession } from "./types";

let current: UserSession | null = null;
let loaded = false;
let loading: Promise<void> | null = null;
let revision = 0;
const listeners = new Set<() => void>();
function emit() {
  for (const listener of listeners) listener();
}
export function getStoredSession(): UserSession | null {
  return current;
}
export function setStoredSession(session: UserSession | null): void {
  // Keep only presentation data in memory, never tokens or arbitrary fields.
  current = session
    ? {
        user: {
          user_id: session.user.user_id,
          email: session.user.email,
          name: session.user.name,
          roles: [...session.user.roles],
        },
      }
    : null;
  loaded = true;
  revision += 1;
  emit();
}
export function clearStoredSession(): void {
  setStoredSession(null);
}
export async function loadStoredSession(force = false): Promise<void> {
  if (loading) return loading;
  if (loaded && !force) return;
  const started = revision;
  loading = (async () => {
    try {
      const { fetchWithAuthRetry } = await import("./api");
      const response = await fetchWithAuthRetry("/api/backend/auth/session", {});
      if (response.ok) {
        const session = await response.json();
        if (revision === started) setStoredSession(session);
      } else if (response.status === 401 && revision === started) clearStoredSession();
    } finally {
      loaded = true;
      loading = null;
      emit();
    }
  })().catch(() => {
    /* A temporary network failure must not claim server logout. */
  });
  return loading;
}
function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}
export function useStoredSession(): UserSession | null {
  const session = useSyncExternalStore(
    subscribe,
    () => current,
    () => null
  );
  useEffect(() => {
    void loadStoredSession();
    const revalidate = () => {
      void loadStoredSession(true);
    };
    window.addEventListener("focus", revalidate);
    return () => window.removeEventListener("focus", revalidate);
  }, []);
  return session;
}
export function useSessionReady(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => loaded,
    () => false
  );
}
