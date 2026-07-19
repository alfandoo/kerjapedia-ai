import { AdminIngestion } from "@/components/admin-ingestion";
import { AdminShell } from "@/components/admin-shell";

export default function AdminIngestionPage() {
  return (
    <AdminShell>
      <AdminIngestion />
    </AdminShell>
  );
}
