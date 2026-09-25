import { AdminShell } from "@/features/admin";
import { SystemOverviewPage } from "@/features/admin/components/admin-system";

export default function SystemPage() {
  return (
    <AdminShell>
      <SystemOverviewPage />
    </AdminShell>
  );
}
