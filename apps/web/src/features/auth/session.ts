"use client";

import { useMemo, useSyncExternalStore } from "react";

export const SESSION_STORAGE_KEY = "kerjapedia-session-v1";
import type { UserSession } from "./types";

function parseStoredSession(raw: string | null): UserSession | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<UserSession>;
    const user = value.user;
    if (
      typeof value.access_token !== "string" ||
      !value.access_token.trim() ||
      !user ||
      typeof user.user_id !== "string" ||
      typeof user.email !== "string" ||
      typeof user.name !== "string" ||
      !Array.isArray(user.roles) ||
      !user.roles.every((role) => typeof role === "string")
    ) {
      return null;
    }
    return value as UserSession;
  } catch {
    return null;
  }
}

export function getStoredSession(): UserSession | null {
  if (typeof window === "undefined") return null;
  return parseStoredSession(window.localStorage.getItem(SESSION_STORAGE_KEY));
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
  return useMemo(() => parseStoredSession(serializedSession), [serializedSession]);
}
