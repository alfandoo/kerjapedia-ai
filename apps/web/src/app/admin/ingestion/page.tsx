import { AdminIngestion } from "@/features/admin";
import { AdminShell } from "@/features/admin";

export default function AdminIngestionPage() {
  return (
    <AdminShell>
      <AdminIngestion />
    </AdminShell>
  );
}
