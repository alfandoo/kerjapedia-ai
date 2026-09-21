import { AdminDashboard } from "@/features/admin";
import { AdminShell } from "@/features/admin";

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const { q } = await searchParams;
  const initialQuery = Array.isArray(q) ? (q[0] ?? "") : (q ?? "");

  return (
    <AdminShell>
      <AdminDashboard initialQuery={initialQuery} />
    </AdminShell>
  );
}
