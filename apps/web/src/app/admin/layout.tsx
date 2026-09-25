import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// Server presence guard: no admin SSR without an HttpOnly session cookie.
// Role authority stays in the backend (`require_admin` → 403) and the
// client AdminShell redirect; this layer only prevents SSR flash for
// browsers with no session at all (including proxy bypasses).
export default async function AdminLayout({ children }: { children: ReactNode }) {
  const store = await cookies();
  const access =
    store.get("__Host-kp-access")?.value ?? store.get("kp-access")?.value;
  if (!access) redirect("/login-admin");
  return <>{children}</>;
}
