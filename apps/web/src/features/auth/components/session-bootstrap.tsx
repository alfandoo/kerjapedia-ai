"use client";
import { useStoredSession } from "../session";
export function SessionBootstrap() {
  useStoredSession();
  return null;
}
