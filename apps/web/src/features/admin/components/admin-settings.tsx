"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  History,
  Shield,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, PageHeader } from "./primitives";
import { cn } from "@/lib/utils";
import {
  fetchAdminSettings,
  fetchAuditLogs,
  type AdminSettings,
  type AuditLogEntry,
} from "@/features/admin/api";

const actionLabels: Record<string, string> = {
  "document.metadata_updated": "Metadata diperbarui",
  "document.published": "Dokumen diterbitkan",
  "document.draft": "Penerbitan dibatalkan",
  "document.uploaded": "PDF diunggah",
  "document.relationships_updated": "Relasi diperbarui",
};

function formatDateTime(value: string) {
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
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [logs, setLogs] = useState<{ entries: AuditLogEntry[]; total: number } | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("Memuat konfigurasi...");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchAdminSettings(controller.signal),
      fetchAuditLogs(page, 10, controller.signal),
    ])
      .then(([settingsData, logsData]) => {
        setSettings(settingsData);
        setLogs(logsData);
        setStatus("Data tersinkron dengan API.");
      })
      .catch(() => setStatus("API belum tersedia — menampilkan nilai bawaan."));
    return () => controller.abort();
  }, [page]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Konfigurasi sistem"
        title="Pengaturan"
        description={status}
        actions={
          settings ? null : (
            <Badge variant="outline" className="text-sm">
              <a
                href="http://127.0.0.1:8000/admin/settings"
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-javanese hover:text-forest"
              >
                Konfigurasi API
              </a>
            </Badge>
          )
        }
      />

      <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="size-4 text-teal" /> Keamanan & layanan
            </CardTitle>
            <CardDescription>Konfigurasi aktif pada API backend</CardDescription>
          </CardHeader>
          <CardContent>
            {settings ? (
              <dl className="space-y-4">
                {[
                  { dt: "Aplikasi", dd: `${settings.app_name} v${settings.app_version}` },
                  { dt: "Email admin", dd: settings.admin_email },
                  {
                    dt: "Batas permintaan",
                    dd: `${settings.rate_limit_per_minute} per menit per IP`,
                  },
                  { dt: "Vector store", dd: settings.vector_store },
                  { dt: "Embedding", dd: settings.embedding_provider },
                  { dt: "Generator jawaban", dd: settings.llm_provider },
                  {
                    dt: "Masa berlaku sesi",
                    dd: formatDuration(settings.session_expires_in_seconds),
                  },
                ].map((row) => (
                  <div
                    key={row.dt}
                    className="flex items-start gap-3 rounded-lg border p-3.5 border-line bg-surface-soft"
                  >
                    <dt className="text-sm font-medium text-tinta flex-1">{row.dt}</dt>
                    <dd className="text-sm font-mono tabular-nums color-emas flex-1">{row.dd}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={index} className="h-12 w-full" />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="size-4 text-teal" /> Audit trail
            </CardTitle>
            <CardDescription>Aktivitas admin terbaru yang tercatat di log sistem</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {logs === null ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={index} className="h-14 w-full" />
                ))}
              </div>
            ) : logs.entries.length === 0 ? (
              <EmptyState
                icon={History}
                title="Belum ada aktivitas admin tercatat"
                hint="Perubahan dokumen, publikasi, dan metadata akan muncul di sini."
              />
            ) : (
              <>
                <ul className="divide-y divide-border/20">
                  {logs.entries.map((entry) => (
                    <li key={entry.audit_id} className="flex items-start gap-3 px-4 py-3">
                      <span
                        className={cn(
                          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
                          entry.action.startsWith("document.metadata")
                            ? "bg-amber-soft text-amber"
                            : entry.action.startsWith("document.uploaded")
                              ? "bg-teal-soft text-teal"
                              : "bg-muted/30 text-muted-foreground"
                        )}
                      >
                        {entry.action.startsWith("document.uploaded") ? (
                          <Database className="size-4" />
                        ) : entry.action.startsWith("document.metadata") ? (
                          <AlertTriangle className="size-4" />
                        ) : (
                          <CheckCircle2 className="size-4" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <strong className="text-sm">
                            {actionLabels[entry.action] ?? entry.action.replaceAll(".", " ")}
                          </strong>
                          <Badge variant="secondary" className="font-mono text-[10px]">
                            {entry.actor}
                          </Badge>
                        </div>
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {entry.target_type}
                          {entry.target_id ? ` › ${entry.target_id}` : ""}
                        </p>
                      </div>
                      <time className="shrink-0 text-xs text-muted-foreground tabular-nums">
                        {formatDateTime(entry.created_at)}
                      </time>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex items-center gap-2">
                  {logs.total > 10 && (
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        disabled={page === 1}
                        aria-label="Halaman sebelumnya"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                      >
                        <ChevronLeft className="size-4" />
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        Halaman {page} dari {((logs.total + 9) / 10) | 0}
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        disabled={page * 10 >= logs.total}
                        aria-label="Halaman berikutnya"
                        onClick={() => setPage((p) => Math.min(((logs.total + 9) / 10) | 0, p + 1))}
                      >
                        <ChevronRight className="size-4" />
                      </Button>
                    </div>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
