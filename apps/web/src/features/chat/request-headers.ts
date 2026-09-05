import { getStoredSession } from "@/features/auth";
const GUEST_STORAGE_KEY = "kerjapedia-guest-v1";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function getGuestId(): string {
  const existing = window.localStorage.getItem(GUEST_STORAGE_KEY);
  if (existing && UUID_PATTERN.test(existing)) return existing;
  const guestId = crypto.randomUUID();
  window.localStorage.setItem(GUEST_STORAGE_KEY, guestId);
  return guestId;
}

export function chatHeaders(contentType = false): HeadersInit {
  const session = getStoredSession();
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    ...(session
      ? {}
      : { "X-KerjaPedia-Guest-ID": getGuestId() }),
  };
}
