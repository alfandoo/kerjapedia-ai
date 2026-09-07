import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const MAX_BODY = 50 * 1024 * 1024;
const AUTH_BODY = 16 * 1024;
const COOKIE_AGE = 30 * 24 * 60 * 60;
const production = process.env.NODE_ENV === "production";
const ACCESS = production ? "__Host-kp-access" : "kp-access";
const GUEST = production ? "__Host-kp-guest" : "kp-guest";
const REFRESH = production ? "__Host-kp-refresh" : "kp-refresh";
const cookieOptions = { httpOnly: true, secure: production, sameSite: "lax" as const, path: "/", maxAge: COOKIE_AGE };
const roots = new Set(["auth", "admin", "chat", "documents", "feedback", "ingestion", "evaluation"]);
const authMethods: Record<string, string> = { login: "POST", register: "POST", refresh: "POST", logout: "POST", session: "GET", me: "GET", profile: "PATCH", google: "POST", account: "DELETE", "verify-email-otp": "POST", "resend-otp": "POST" };

type Context = { params: Promise<{ path: string[] }> };
function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store", "Vary": "Cookie", "X-Content-Type-Options": "nosniff" } });
}
function clearCookies(response: NextResponse) {
  for (const name of [ACCESS, REFRESH]) response.cookies.set(name, "", { ...cookieOptions, maxAge: 0 });
  return response;
}
function publicUser(value: unknown) {
  if (!value || typeof value !== "object") return null;
  const user = value as Record<string, unknown>;
  if (![user.user_id, user.email, user.name].every(x => typeof x === "string") || !Array.isArray(user.roles) || !user.roles.every(x => typeof x === "string")) return null;
  return { user_id: user.user_id, email: user.email, name: user.name, roles: user.roles };
}
async function smallJson(request: NextRequest) {
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > AUTH_BODY) { await reader.cancel(); throw new Error("body_limit"); }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}
async function readDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const detail = (body as Record<string, unknown>).detail;
      if (typeof detail === "string" && detail.length > 0 && detail.length <= 160) return detail;
    }
  } catch {
    /* fall through to generic message */
  }
  return null;
}

async function handle(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || !roots.has(path[0]) || path.some(p => !/^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*$/.test(p))) return json({ detail: "Not found." }, 404);
  const auth = path[0] === "auth";
  const action = path[1];
  if (auth && (path.length !== 2 || !authMethods[action])) return json({ detail: "Not found." }, 404);
  if (auth && request.method !== authMethods[action]) return json({ detail: "Method not allowed." }, 405);
  // Require both an exact trusted origin and a non-simple header on mutations,
  // including login and refresh. Do not trust forwarded Host/Origin headers.
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
    const expectedOrigin = process.env.APP_ORIGIN ? new URL(process.env.APP_ORIGIN).origin : request.nextUrl.origin;
    if (request.headers.get("origin") !== expectedOrigin || request.headers.get("x-kerjapedia-csrf") !== "1" || request.headers.get("sec-fetch-site") === "cross-site") return json({ detail: "Cross-site request rejected." }, 403);
  }
  if (request.method === "OPTIONS") return json({ detail: "Method not allowed." }, 405);

  const access = request.cookies.get(ACCESS)?.value;
  const refresh = request.cookies.get(REFRESH)?.value;
  if (auth && action === "refresh" && !refresh) return clearCookies(json({ detail: "Session expired." }, 401));
  if (auth && ["session", "me", "profile", "account"].includes(action) && !access) return json({ detail: "No active session." }, 401);
  if (auth && action === "logout" && !access) {
    // A refresh cookie may still be valid: let the client refresh then revoke.
    return refresh ? json({ detail: "Session refresh required." }, 401) : clearCookies(json({ status: "ok" }));
  }
  const storedGuest = request.cookies.get(GUEST)?.value;
  const guestRequest = !auth && ["chat", "feedback"].includes(path[0]) && !access;
  const validGuest = storedGuest && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(storedGuest);
  const guest = guestRequest ? (validGuest ? storedGuest : randomUUID()) : null;
  let oversized = false;
  try {
    const base = new URL(process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw Error("Invalid backend configuration");
    const targetPath = auth && action === "session" ? "auth/me" : path.map(encodeURIComponent).join("/");
    const target = new URL(base.href.replace(/\/$/, "") + "/" + targetPath);
    target.search = request.nextUrl.search;
    const headers = new Headers();
    for (const name of ["content-type", "accept", "range"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    if (guest) headers.set("x-kerjapedia-guest-id", guest);
    // Browser Authorization and Cookie headers are never forwarded.
    if (access && !(auth && ["login", "register", "refresh", "google", "verify-email-otp", "resend-otp"].includes(action))) headers.set("Authorization", `Bearer ${access}`);
    let body: BodyInit | null = null;
    if (auth && ["login", "register"].includes(action)) {
      const input = await smallJson(request);
      body = JSON.stringify(action === "register" ? { name: input.name, email: input.email, password: input.password } : { email: input.email, password: input.password });
      headers.set("content-type", "application/json");
    } else if (auth && ["verify-email-otp", "resend-otp"].includes(action)) {
      const input = await smallJson(request);
      const allowed = action === "verify-email-otp"
        ? ["email", "token"]
        : ["email"];
      if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some(key => !allowed.includes(key))) return json({ detail: "Invalid verification payload." }, 400);
      if (typeof input.email !== "string" || !input.email || (action === "verify-email-otp" && (typeof input.token !== "string" || !input.token))) return json({ detail: "Invalid verification payload." }, 400);
      body = JSON.stringify(action === "verify-email-otp" ? { email: input.email, token: input.token } : { email: input.email });
      headers.set("content-type", "application/json");
    } else if (auth && action === "google") {
      const input = await smallJson(request);
      if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some(key => key !== "id_token") || typeof input.id_token !== "string" || !input.id_token) return json({ detail: "Invalid Google credential." }, 400);
      body = JSON.stringify({ id_token: input.id_token });
      headers.set("content-type", "application/json");
    } else if (auth && action === "profile") {
      const input = await smallJson(request);
      if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some(key => key !== "name")) return json({ detail: "Invalid profile fields." }, 400);
      body = JSON.stringify({ name: input.name });
      headers.set("content-type", "application/json");
    } else if (auth && action === "refresh") {
      body = JSON.stringify({ refresh_token: refresh });
      headers.set("content-type", "application/json");
    } else if (!["GET", "HEAD"].includes(request.method) && !(auth && action === "logout")) {
      const declared = request.headers.get("content-length");
      if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_BODY)) return json({ detail: "Upload exceeds the 50 MB limit." }, 413);
      let size = 0;
      body = request.body?.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          size += chunk.byteLength;
          if (size > MAX_BODY) { oversized = true; throw Error("body_limit"); }
          controller.enqueue(chunk);
        },
      })) ?? null;
    }
    const options: RequestInit & { duplex?: "half" } = { method: request.method, headers, body, cache: "no-store", redirect: "manual", signal: request.signal };
    if (body instanceof ReadableStream) options.duplex = "half";
    const upstream = await fetch(target, options);
    if (upstream.status >= 300 && upstream.status < 400) return json({ detail: "Unexpected backend redirect." }, 502);
    if (auth) {
      if (!upstream.ok) {
        // Expose the backend's detail only for specific client errors where it
        // is safe and user-relevant (e.g. duplicate email, invalid fields).
        // For actions without an active session, a 401 means "invalid
        // credentials/code" (not an expired session), so pass it through.
        let detail: string | null = null;
        const unauthenticated = ["login", "register", "google", "verify-email-otp", "resend-otp"];
        const passthrough = [...unauthenticated, "session", "me", "profile"].includes(action)
          ? [400, 401, 403, 404, 409, 422]
          : [400, 403, 404, 409, 422];
        if (passthrough.includes(upstream.status)) {
          detail = await readDetail(upstream);
        }
        const response = detail
          ? json({ detail }, upstream.status)
          : json({ detail: upstream.status === 401 ? "Sesi berakhir atau kredensial tidak valid." : "Permintaan autentikasi gagal. Silakan coba lagi." }, upstream.status);
        return action === "refresh" && [400, 401, 403].includes(upstream.status) ? clearCookies(response) : response;
      }
      if (action === "logout") return clearCookies(json({ status: "ok" }));
      if (action === "account") return clearCookies(json({ status: "deleted" }));
      if (action === "resend-otp") return json({ status: "resent" });
      const result = await upstream.json();
      if (["session", "me", "profile"].includes(action)) {
        const user = publicUser(result);
        return user ? json({ user }) : json({ detail: "Invalid session response." }, 502);
      }
      const user = publicUser(result.user);
      if (action === "register" && !result.access_token) return json({ requires_email_confirmation: true }, 202);
      if (!user || typeof result.access_token !== "string" || !result.access_token || typeof result.refresh_token !== "string" || !result.refresh_token) return json({ detail: "Invalid session response." }, 502);
      const response = json({ user });
      response.cookies.set(ACCESS, result.access_token, cookieOptions);
      response.cookies.set(REFRESH, result.refresh_token, cookieOptions);
      return response;
    }
    const responseHeaders = new Headers({ "Cache-Control": "private, no-store", "Vary": "Cookie", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-disposition", "content-range", "accept-ranges", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
    if (guest && !validGuest) response.cookies.set(GUEST, guest, { ...cookieOptions, maxAge: 31536000 });
    return response;
  } catch (error) {
    if (oversized || (error instanceof Error && error.message === "body_limit")) return json({ detail: "Request body is too large." }, 413);
    if (error instanceof SyntaxError) return json({ detail: "Invalid request body." }, 400);
    return json({ detail: "API tidak dapat dihubungi. Silakan coba lagi." }, 503);
  }
}
export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE, handle as HEAD, handle as OPTIONS };
