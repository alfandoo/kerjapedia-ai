import { AdminShell } from "@/features/admin";
import { SystemTracesPage } from "@/features/admin/components/admin-system";

export default function SystemTracesRoute() {
  return (
    <AdminShell>
      <SystemTracesPage />
    </AdminShell>
  );
}
