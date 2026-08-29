import { AdminDashboard } from "@/features/admin";
import { AdminShell } from "@/features/admin";

export default function DocumentsPage() {
  return (
    <AdminShell>
      <AdminDashboard />
    </AdminShell>
  );
}
