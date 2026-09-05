import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const development = process.env.NODE_ENV !== "production";
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    "script-src-attr 'none'",
    // Radix and the existing theme/progress components use inline styles.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${development ? " ws: wss:" : ""}`,
    "object-src 'none'",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
  ].join("; ");
  const headers = new Headers(request.headers);
  // Replace client-supplied values before Next renders its own script tags.
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  const guestName = development ? "kp-guest" : "__Host-kp-guest";
  const guest = request.cookies.get(guestName)?.value;
  if (!guest || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(guest)) {
    response.cookies.set(guestName, crypto.randomUUID(), { httpOnly: true, secure: !development, sameSite: "lax", path: "/", maxAge: 31536000 });
  }
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  matcher: ["/((?!api/backend|_next/static|_next/image|favicon.ico).*)"],
};
