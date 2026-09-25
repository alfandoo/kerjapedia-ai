import { AdminShell } from "@/features/admin";
import { SystemServicesPage } from "@/features/admin/components/admin-system";

export default function SystemServicesRoute() {
  return (
    <AdminShell>
      <SystemServicesPage />
    </AdminShell>
  );
}
