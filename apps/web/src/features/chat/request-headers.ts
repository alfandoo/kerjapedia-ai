// The BFF supplies authentication and guest identity from server-managed cookies.
export function chatHeaders(contentType = false): HeadersInit {
  return contentType ? { "Content-Type": "application/json" } : {};
}
