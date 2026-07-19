import { AdminShell } from "@/components/admin-shell";

export default function AdminSettingsPage() {
  return (
    <AdminShell>
      <section className="admin-standard-page">
        <div className="admin-page-heading">
          <div>
            <h1>Pengaturan</h1>
            <p>Konfigurasi admin menggunakan environment aplikasi pada tahap MVP.</p>
          </div>
        </div>
      </section>
    </AdminShell>
  );
}
