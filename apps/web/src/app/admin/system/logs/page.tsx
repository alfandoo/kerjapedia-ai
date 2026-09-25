import { AdminShell } from "@/features/admin";
import { SystemLogsPage } from "@/features/admin/components/admin-system";

export default function SystemLogsRoute() {
  return (
    <AdminShell>
      <SystemLogsPage />
    </AdminShell>
  );
}
