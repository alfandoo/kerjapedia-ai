"use client";

import { useMemo, useSyncExternalStore } from "react";

export const SESSION_STORAGE_KEY = "kerjapedia-session-v1";
import type { UserSession } from "./types";

export function getStoredSession(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
  window.dispatchEvent(new Event("kerjapedia-session-change"));
}

function subscribe(callback: () => void) {
  window.addEventListener("kerjapedia-session-change", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("kerjapedia-session-change", callback);
    window.removeEventListener("storage", callback);
  };
}

function getClientSnapshot() {
  return window.localStorage.getItem(SESSION_STORAGE_KEY);
}

function getServerSnapshot() {
  return null;
}

export function useStoredSession(): UserSession | null {
  const serializedSession = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);

  return useMemo(() => {
    if (!serializedSession) return null;
    try {
      return JSON.parse(serializedSession) as UserSession;
    } catch {
      return null;
    }
  }, [serializedSession]);
}
