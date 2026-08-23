"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, History, Shield } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, PageHeader } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import {
  fetchAdminSettings,
  fetchAuditLogs,
  type AdminSettings,
  type AuditLogEntry,
} from "@/lib/api";

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

export function AdminSettings() {
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [logs, setLogs] = useState<AuditLogEntry[] | null>(null);
  const [status, setStatus] = useState("Memuat konfigurasi...");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchAdminSettings(controller.signal), fetchAuditLogs(100, controller.signal)])
      .then(([settingsData, logsData]) => {
        setSettings(settingsData);
        setLogs(logsData);
        setStatus("Data tersinkron dengan API.");
      })
      .catch(() => setStatus("API belum tersedia — menampilkan nilai bawaan."));
    return () => controller.abort();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Konfigurasi sistem" title="Pengaturan" description={status} />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="size-4 text-teal" /> Keamanan & layanan
            </CardTitle>
            <CardDescription>Konfigurasi aktif pada API backend</CardDescription>
          </CardHeader>
          <CardContent>
            {settings ? (
              <dl className="space-y-3">
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
                    dd: `${Math.round(settings.session_expires_in_seconds / 60)} menit`,
                  },
                ].map((row) => (
                  <div
                    key={row.dt}
                    className="flex items-center justify-between gap-4 rounded-lg border px-3 py-2.5"
                  >
                    <dt className="text-sm text-muted-foreground">{row.dt}</dt>
                    <dd className="truncate font-mono text-sm font-medium tabular-nums">
                      {row.dd}
                    </dd>
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

        <Card className="lg:col-span-3">
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
            ) : logs.length === 0 ? (
              <EmptyState
                icon={History}
                title="Belum ada aktivitas admin tercatat"
                hint="Perubahan dokumen, publikasi, dan metadata akan muncul di sini."
              />
            ) : (
              <ul className="divide-y">
                {logs.map((entry) => (
                  <li key={entry.audit_id} className="flex items-start gap-3 px-4 py-3">
                    <span
                      className={cn(
                        "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
                        entry.action.startsWith("document.metadata")
                          ? "bg-amber-soft text-amber"
                          : entry.action.startsWith("document.uploaded")
                            ? "bg-teal-soft text-teal"
                            : "bg-muted text-muted-foreground"
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
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
