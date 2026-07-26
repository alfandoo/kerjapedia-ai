"use client";

import { useMemo, useSyncExternalStore } from "react";

import { SESSION_STORAGE_KEY } from "@/lib/api";
import type { UserSession } from "@/lib/types";

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
