import { AdminShell } from "@/features/admin";
import { SystemAlertsPage } from "@/features/admin/components/admin-system";

export default function SystemAlertsRoute() {
  return (
    <AdminShell>
      <SystemAlertsPage />
    </AdminShell>
  );
}
