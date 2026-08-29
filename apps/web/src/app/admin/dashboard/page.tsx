import { AdminDashboardPage } from "@/features/admin";
import { AdminShell } from "@/features/admin";

export default function DashboardPage() {
  return (
    <AdminShell>
      <AdminDashboardPage />
    </AdminShell>
  );
}
