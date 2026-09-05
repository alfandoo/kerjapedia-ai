"use client";
import { useEffect, useState } from "react";
import { Database, History, RefreshCw, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { EmptyState, PageHeader } from "./primitives";
import { fetchAdminSettings, fetchAuditLogs } from "@/features/admin/api";
import type { AdminSettings as SettingsData, AuditLogEntry } from "@/features/admin/types";
import styles from "./admin-ingestion.module.css";

const actionLabels: Record<string, string> = {
  "document.metadata_updated": "Metadata diperbarui",
  "document.published": "Dokumen diterbitkan",
  "document.draft": "Penerbitan dibatalkan",
  "document.uploaded": "PDF diunggah",
  "document.relationships_updated": "Relasi diperbarui",
};

function formatDateTime(value: string) {
  if (Number.isNaN(new Date(value).getTime())) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${seconds} detik`;
  const mins = Math.round(seconds / 60);
  if (mins >= 1440) {
    const days = Math.floor(mins / 1440);
    return `${days} hari`;
  }
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours} jam ${remainingMins > 0 ? `${remainingMins} menit` : ""}`;
  }
  return `${mins} menit`;
}

export function AdminSettings() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [logs, setLogs] = useState<{ entries: AuditLogEntry[]; total: number } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState(false);
  const [logsError, setLogsError] = useState(false);
  const [settingsReload, setSettingsReload] = useState(0);
  const [logsReload, setLogsReload] = useState(0);
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminSettings(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setSettings(data);
        setSettingsError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setSettingsError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSettingsLoading(false);
      });
    return () => controller.abort();
  }, [settingsReload]);

  useEffect(() => {
    const controller = new AbortController();
    fetchAuditLogs(page, pageSize, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const lastPage = Math.max(1, Math.ceil(data.total / pageSize));
        if (page > lastPage) {
          setPage(lastPage);
          return;
        }
        setLogs(data);
        setLogsError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLogsError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLogsLoading(false);
      });
    return () => controller.abort();
  }, [page, pageSize, logsReload]);

  const reloadSettings = () => {
    setSettingsLoading(true);
    setSettingsError(false);
    setSettingsReload((value) => value + 1);
  };
  const reloadLogs = () => {
    setLogsLoading(true);
    setLogsError(false);
    setLogsReload((value) => value + 1);
  };
  const changePage = (next: number) => {
    setLogsLoading(true);
    setPage(next);
  };
  const pageCount = Math.max(1, Math.ceil((logs?.total ?? 0) / pageSize));

  return (
    <div className={`${styles.ingestion} space-y-6`}>
      <PageHeader
        eyebrow="Administrasi"
        title="Pengaturan"
        description="Lihat konfigurasi layanan yang aktif dan riwayat aktivitas admin."
        actions={
          <Button
            variant="outline"
            disabled={settingsLoading || logsLoading}
            onClick={() => {
              reloadSettings();
              reloadLogs();
            }}
          >
            <RefreshCw className="size-4" /> Muat ulang
          </Button>
        }
      />
      <section aria-label="Konfigurasi aktif">
        {settingsLoading ? (
          <div
            className="grid gap-4 md:grid-cols-2"
            aria-busy="true"
            aria-label="Memuat konfigurasi"
          >
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : settingsError ? (
          <div role="alert" className="rounded-xl border border-line bg-white p-6">
            <p className="text-sm text-red">Konfigurasi belum dapat dimuat.</p>
            <Button variant="outline" className="mt-3" onClick={reloadSettings}>
              Coba lagi
            </Button>
          </div>
        ) : (
          settings && (
            <>
              <div className="grid items-start gap-6 lg:grid-cols-2">
                {[
                  {
                    title: "Akun & keamanan",
                    icon: Shield,
                    description: "Identitas admin dan batas akses layanan.",
                    rows: [
                      ["Email admin", settings.admin_email],
                      ["Batas permintaan", `${settings.rate_limit_per_minute} per menit per IP`],
                      ["Masa berlaku sesi", formatDuration(settings.session_expires_in_seconds)],
                    ],
                  },
                  {
                    title: "Layanan RAG",
                    icon: Database,
                    description: "Konfigurasi yang dilaporkan oleh backend API.",
                    rows: [
                      ["Aplikasi", `${settings.app_name} · v${settings.app_version}`],
                      ["Vector store", settings.vector_store],
                      ["Embedding provider", settings.embedding_provider],
                      ["Answer generator", settings.llm_provider],
                    ],
                  },
                ].map((group) => (
                  <Card key={group.title}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <group.icon className="size-5 text-forest" />
                        {group.title}
                      </CardTitle>
                      <CardDescription>{group.description}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <dl className="divide-y divide-line">
                        {group.rows.map(([label, value]) => (
                          <div
                            key={label}
                            className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] sm:gap-4"
                          >
                            <dt className="text-sm text-muted-text">{label}</dt>
                            <dd className="break-words text-sm font-medium text-tinta">
                              {value || "—"}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <p className="mt-3 text-xs text-muted-text">
                Konfigurasi ini hanya dapat dilihat. Perubahan dilakukan melalui konfigurasi
                backend.
              </p>
            </>
          )
        )}
      </section>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="size-5 text-forest" />
            Audit trail
          </CardTitle>
          <CardDescription>
            Riwayat perubahan dokumen dan aktivitas admin yang tercatat di sistem.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {logsLoading ? (
            <div className="space-y-3 p-6" aria-busy="true" aria-label="Memuat aktivitas">
              {Array.from({ length: 5 }, (_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : logsError ? (
            <div role="alert" className="px-6 pb-6">
              <p className="text-sm text-red">Riwayat aktivitas belum dapat dimuat.</p>
              <Button variant="outline" className="mt-3" onClick={reloadLogs}>
                Coba lagi
              </Button>
            </div>
          ) : !logs?.entries.length ? (
            <EmptyState
              icon={History}
              title="Belum ada aktivitas tercatat"
              hint="Perubahan metadata dan publikasi dokumen akan muncul di sini."
            />
          ) : (
            <>
              <Table aria-label="Riwayat aktivitas admin" className="min-w-[720px]">
                <TableHeader className="bg-surface-soft">
                  <TableRow className="border-line">
                    {["Aktivitas", "Admin", "Waktu", "Tindakan"].map((label) => (
                      <TableHead key={label} scope="col" className="px-4 text-muted-text">
                        {label}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.entries.map((entry) => (
                    <TableRow key={entry.audit_id} className="border-line">
                      <TableCell className="max-w-xs whitespace-normal px-4 py-4">
                        <p className="font-medium text-tinta">
                          {actionLabels[entry.action] ?? entry.action.replaceAll(".", " ")}
                        </p>
                        <p className="mt-1 break-all text-xs text-muted-text">
                          {entry.target_type}
                          {entry.target_id ? ` · ${entry.target_id}` : ""}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-48 whitespace-normal break-all px-4 text-xs text-muted-text">
                        {entry.actor}
                      </TableCell>
                      <TableCell className="px-4 text-xs text-muted-text">
                        {formatDateTime(entry.created_at)}
                      </TableCell>
                      <TableCell className="px-4">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelected(entry)}
                          aria-label={`Detail aktivitas ${entry.audit_id}`}
                        >
                          Detail
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-muted-text">
                <label className="flex items-center gap-2">
                  Baris per halaman
                  <select
                    className="min-h-9 rounded-md border border-line bg-white px-2 text-tinta"
                    value={pageSize}
                    onChange={(event) => {
                      setLogsLoading(true);
                      setPageSize(Number(event.target.value));
                      setPage(1);
                    }}
                  >
                    {[5, 10, 20, 50].map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
                <span role="status">
                  {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, logs.total)} dari{" "}
                  {logs.total} aktivitas
                </span>
                <nav aria-label="Pagination audit trail" className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page === 1}
                    onClick={() => changePage(page - 1)}
                  >
                    Sebelumnya
                  </Button>
                  <span>
                    {page} / {pageCount}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page >= pageCount}
                    onClick={() => changePage(page + 1)}
                  >
                    Berikutnya
                  </Button>
                </nav>
              </div>
            </>
          )}
        </CardContent>
      </Card>
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent
          className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-xl`}
        >
          <DialogHeader className="pr-8">
            <DialogTitle>Detail aktivitas</DialogTitle>
            <DialogDescription>
              {selected && (actionLabels[selected.action] ?? selected.action.replaceAll(".", " "))}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <dl className="space-y-4">
              {[
                ["Admin", selected.actor],
                ["Waktu", formatDateTime(selected.created_at)],
                [
                  "Target",
                  `${selected.target_type}${selected.target_id ? ` · ${selected.target_id}` : ""}`,
                ],
                ["ID aktivitas", selected.audit_id],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-muted-text">{label}</dt>
                  <dd className="mt-1 break-all text-sm text-tinta">{value}</dd>
                </div>
              ))}
              <div className="border-t border-line pt-4">
                <dt className="mb-2 text-xs text-muted-text">Rincian perubahan</dt>
                <dd>
                  {Object.keys(selected.details).length ? (
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-surface-soft p-4 text-xs text-tinta">
                      {JSON.stringify(selected.details, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-sm text-muted-text">Tidak ada rincian tambahan.</p>
                  )}
                </dd>
              </div>
            </dl>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
