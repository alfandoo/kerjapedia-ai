import { AdminDashboardPage } from "@/components/admin-dashboard-page";
import { AdminShell } from "@/components/admin-shell";

export default function DashboardPage() {
  return (
    <AdminShell>
      <AdminDashboardPage />
    </AdminShell>
  );
}
