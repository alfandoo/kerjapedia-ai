"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import {
  Activity,
  Bell,
  FileText,
  Gauge,
  Monitor,
  RefreshCw,
  Server,
  Timer,
  Workflow,
} from "lucide-react";

import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { AlertIcon } from "@/components/icons";
import { Skeleton } from "@/components/ui/skeleton";
import {
  clearStoredSession,
  fetchSystemAlerts,
  fetchSystemLogs,
  fetchSystemOverview,
  fetchSystemServices,
  fetchSystemTrace,
  fetchSystemTraces,
} from "@/features/admin/api";
import type {
  AlertEvent,
  AlertRule,
  SystemLogEntry,
  SystemOverview,
  SystemServiceStatus,
  SystemTraceDetail,
  SystemTraceSummary,
} from "@/features/admin/types";
import { cn } from "@/lib/utils";
import styles from "./admin-dashboard.module.css";

function formatInt(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("id-ID").format(Math.round(value));
}

function formatMs(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value >= 1000
    ? `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value / 1000)} dtk`
    : `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(value)} ms`;
}

function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value * 100)}%`;
}

function formatUptime(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}h ${hours}j`;
  if (hours > 0) return `${hours}j ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}dtk`;
  return `${seconds}dtk`;
}

function formatTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function InlineSpinner({ label = "Memuat..." }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-1.5 text-xs text-muted-text">
      <RefreshCw aria-hidden="true" className="size-3.5 animate-spin motion-reduce:animate-none" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

function useAdminFetch<T>(loader: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    // Background-refetch indicator only; not in deps so no render loop.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (data !== null) setFetching(true);
    loader(controller.signal)
      .then((result) => {
        setData(result);
        setLoading(false);
        setFetching(false);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "Gagal memuat data.";
        if (message === "Invalid or expired token." || message === "Missing bearer token.") {
          clearStoredSession();
          router.push("/login-admin");
          return;
        }
        setError(message);
        setLoading(false);
        setFetching(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, reloadKey, ...deps]);
  return {
    data,
    loading,
    fetching,
    error,
    reload: () => {
      setError(null);
      setLoading(true);
      setData(null);
      setReloadKey((value) => value + 1);
    },
  };
}

function useDebouncedValue(value: string, delayMs = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function Card({
  title,
  hint,
  icon: Icon,
  children,
}: {
  title: string;
  hint: string;
  icon: ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
      <header className="border-b border-[#e5e5e5] px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
            <Icon className="size-4 text-forest" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-forest">{title}</h2>
            <p className="mt-0.5 text-xs text-muted-text">{hint}</p>
          </div>
        </div>
      </header>
      <div className="space-y-5 px-6 py-5">{children}</div>
    </section>
  );
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-64 items-center justify-center" role="alert">
      <div className="w-full max-w-sm rounded-xl border border-[#e5e5e5] bg-white p-2 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
        <EmptyState
          icon={AlertIcon}
          title="Data tidak dapat dimuat"
          hint={message}
          action={
            <button
              type="button"
              className="h-10 rounded-xl border border-[#e5e5e5] bg-white px-5 text-sm font-semibold text-forest transition hover:border-forest hover:text-teal"
              onClick={onRetry}
            >
              Muat ulang
            </button>
          }
        />
      </div>
    </div>
  );
}

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "healthy" || status === "ready" || status === "ok") return "success";
  if (status === "degraded" || status === "unknown") return "warning";
  return "danger";
}

function statusLabel(status: string) {
  if (status === "healthy") return "Healthy";
  if (status === "degraded") return "Degraded";
  if (status === "down") return "Down";
  if (status === "unknown") return "Unknown";
  if (status === "critical") return "Critical";
  return status;
}

// ---------------------------------------------------------------- overview

export function SystemOverviewPage() {
  const [windowHours, setWindowHours] = useState(24);
  const { data, loading, fetching, error, reload } = useAdminFetch<SystemOverview>(
    (signal) => fetchSystemOverview(windowHours, signal),
    [windowHours]
  );

  if (loading) {
    return (
      <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`} role="status" aria-label="Memuat system monitoring">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[112px] rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }
  if (error || !data) return <LoadError message={error ?? "Coba muat ulang."} onRetry={reload} />;

  const kpis = [
    { key: "req", label: "Requests", value: formatInt(data.requests.total), footer: `${formatInt(data.requests.rate_per_minute)}/menit` },
    { key: "err", label: "Error Rate", value: formatPct(data.requests.error_rate), footer: `${formatInt(data.requests.failed_5xx)} × 5xx · ${formatInt(data.requests.count_4xx)} × 4xx` },
    { key: "p95", label: "P95 Latency", value: formatMs(data.latency_ms.p95_ms), footer: `p50 ${formatMs(data.latency_ms.p50_ms)} · p99 ${formatMs(data.latency_ms.p99_ms)}` },
    { key: "up", label: "Uptime", value: formatUptime(data.uptime_seconds), footer: "per proses (reset saat deploy)" },
  ];
  const services = Object.entries(data.dependencies);

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="System Monitoring"
        title="System Overview"
        description={`Kesehatan aplikasi, API, dan dependensi — ${windowHours} jam terakhir. Metrik kualitas RAG ada di Observability.`}
        actions={
          <div className="flex items-center gap-2">
            {fetching ? <InlineSpinner label="Memuat ulang metrik..." /> : null}
            <span
              className={cn(
                "inline-flex items-center rounded-full px-3 py-1.5 text-xs font-bold",
                data.status === "healthy" && "bg-teal-soft text-forest",
                data.status === "degraded" && "bg-amber-soft text-amber",
                data.status === "critical" && "bg-red/10 text-red"
              )}
            >
              {statusLabel(data.status)}
            </span>
            <div role="group" aria-label="Rentang waktu" className="flex overflow-hidden rounded-xl border border-[#e5e5e5] bg-white">
              {[24, 168].map((hours) => (
                <button
                  key={hours}
                  type="button"
                  aria-pressed={windowHours === hours}
                  onClick={() => setWindowHours(hours)}
                  className={cn(
                    "h-10 px-4 text-sm font-semibold transition",
                    windowHours === hours ? "bg-forest text-white" : "text-muted-text hover:text-forest"
                  )}
                >
                  {hours === 24 ? "24 jam" : "7 hari"}
                </button>
              ))}
            </div>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((card) => (
          <div key={card.key} className="rounded-xl border border-[#e5e5e5] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
            <p className="truncate text-xs font-medium text-muted-text">{card.label}</p>
            <p className="mt-0.5 font-mono text-xl leading-tight font-bold tracking-tight whitespace-nowrap text-tinta tabular-nums">
              {card.value}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-text">{card.footer}</p>
          </div>
        ))}
      </div>

      <Card title="Service Health" hint="Status dan latensi terakhir tiap dependensi." icon={Server}>
        <ul className="divide-y divide-[#eef1ee]">
          {services.map(([name, info]) => (
            <li key={name} className="flex items-center gap-3 py-2.5">
              <StatusBadge tone={statusTone(info.status)}>{statusLabel(info.status)}</StatusBadge>
              <span className="min-w-0 flex-1 truncate font-mono text-sm text-tinta">{name}</span>
              <span className="font-mono text-sm font-semibold text-tinta tabular-nums">{formatMs(info.latency_ms)}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Request Performance" hint="Latensi p50/p95/p99 dari bucket per-menit." icon={Timer}>
        <dl className="space-y-3.5">
          {[
            { label: "p50", value: data.latency_ms.p50_ms },
            { label: "p95", value: data.latency_ms.p95_ms },
            { label: "p99", value: data.latency_ms.p99_ms },
          ].map((row) => (
            <div key={row.label}>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-sm text-muted-text">{row.label}</dt>
                <dd className="font-mono text-sm font-semibold text-tinta tabular-nums">{formatMs(row.value)}</dd>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#e9edea]">
                <div
                  className="h-full rounded-full bg-forest"
                  style={{
                    width: `${data.latency_ms.p99_ms ? Math.min(100, ((row.value ?? 0) / data.latency_ms.p99_ms) * 100) : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </dl>
      </Card>

      <Card title="Recent Errors" hint="10 error terbaru dari system log." icon={FileText}>
        {data.recent_errors.length > 0 ? (
          <ul className="divide-y divide-[#eef1ee]">
            {data.recent_errors.map((log) => (
              <li key={log.log_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className="text-xs text-muted-text">{formatTime(log.timestamp)}</span>
                <span className="font-mono text-tinta">{log.service}</span>
                <span className="min-w-0 flex-1 truncate text-muted-text">{log.message}</span>
                {log.request_id ? (
                  <span className="font-mono text-xs text-muted-text">{log.request_id.slice(0, 8)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-text">Tidak ada error pada rentang ini.</p>
        )}
      </Card>

      <Card title="Active Alerts" hint="Aturan yang sedang firing." icon={Bell}>
        {data.active_alerts.length > 0 ? (
          <ul className="space-y-2">
            {data.active_alerts.map((alert) => (
              <li key={alert.rule} className="flex items-center gap-2 text-sm">
                <StatusBadge tone={alert.severity === "critical" ? "danger" : "warning"}>
                  {alert.severity}
                </StatusBadge>
                <span className="font-mono text-tinta">{alert.rule}</span>
                <span className="min-w-0 flex-1 truncate text-muted-text">{alert.message}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-text">Tidak ada alert aktif.</p>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- services

export function SystemServicesPage() {
  const { data, loading, fetching, error, reload } = useAdminFetch<{ services: SystemServiceStatus[] }>(
    (signal) => fetchSystemServices(signal)
  );
  const [expanded, setExpanded] = useState<string | null>(null);

  if (loading) {
    return (
      <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`} role="status" aria-label="Memuat services">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }
  if (error || !data) return <LoadError message={error ?? "Coba muat ulang."} onRetry={reload} />;

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="System Monitoring"
        title="Services"
        description="Health check ringan tiap dependensi. Tanpa query mahal atau LLM call berbayar."
        actions={
          <div className="flex items-center gap-2">
            {fetching ? <InlineSpinner label="Memeriksa services..." /> : null}
            <button type="button" className={styles.upload} onClick={reload} disabled={fetching}>
              <RefreshCw className={cn("size-4", fetching && "animate-spin motion-reduce:animate-none")} strokeWidth={2} /> Muat ulang
            </button>
          </div>
        }
      />
      <Card title="Service Health" hint="Klik baris untuk detail latensi, error rate, dan insiden." icon={Server}>
        <ul className="divide-y divide-[#eef1ee]">
          {data.services.map((service) => {
            const open = expanded === service.service;
            return (
              <li key={service.service}>
                <button
                  type="button"
                  className="flex w-full items-center gap-3 py-3 text-left"
                  aria-expanded={open}
                  onClick={() => setExpanded(open ? null : service.service)}
                >
                  <StatusBadge tone={statusTone(service.status)}>{statusLabel(service.status)}</StatusBadge>
                  <span className="min-w-0 flex-1 truncate font-mono text-sm text-tinta">{service.service}</span>
                  <span className="font-mono text-sm font-semibold text-tinta tabular-nums">
                    {formatMs(service.latency_ms)}
                  </span>
                </button>
                {open ? (
                  <div className="space-y-2 rounded-lg bg-[#f2f5f3] px-4 py-3 text-sm">
                    <p className="text-muted-text">
                      Terakhir dicek: {formatTime(service.last_checked)} · Rerata 24 jam:{" "}
                      {formatMs(service.avg_24h_ms)} · Error rate 24 jam:{" "}
                      {service.error_rate_24h === null || service.error_rate_24h === undefined
                        ? "—"
                        : `${(service.error_rate_24h * 100).toFixed(1)}%`}
                    </p>
                    {service.error ? <p className="text-red">{service.error}</p> : null}
                    {service.recent_incidents.length > 0 ? (
                      <ul className="space-y-1">
                        {service.recent_incidents.map((incident, index) => (
                          <li key={index} className="font-mono text-xs text-muted-text">
                            {formatTime(incident.checked_at)} · {incident.status} ·{" "}
                            {formatMs(incident.latency_ms)} · {incident.error ?? "—"}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-text">Tidak ada insiden 7 hari terakhir.</p>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- logs

const LOG_LEVELS = ["", "debug", "info", "warn", "error"];
const LOG_STATUS = ["", "ok", "error"];

export function SystemLogsPage() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search);
  const [level, setLevel] = useState("");
  const [service, setService] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<SystemLogEntry | null>(null);
  const limit = 50;
  const { data, loading, fetching, error, reload } = useAdminFetch<{ entries: SystemLogEntry[]; total: number }>(
    (signal) => fetchSystemLogs({ search: debouncedSearch, level, service, status: statusFilter, limit, offset }, signal),
    [debouncedSearch, level, service, statusFilter, offset]
  );

  if (error) return <LoadError message={error} onRetry={reload} />;
  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="System Monitoring"
        title="Logs"
        description="Error dan warning terstruktur. Info/debug hanya di stdout platform."
        actions={
          <div className="flex items-center gap-2">
            {fetching ? <InlineSpinner label="Memuat log..." /> : null}
            <button type="button" className={styles.upload} onClick={reload} disabled={fetching}>
              <RefreshCw className={cn("size-4", fetching && "animate-spin motion-reduce:animate-none")} strokeWidth={2} /> Muat ulang
            </button>
          </div>
        }
      />
      <Card title="Filter" hint="Pencarian pesan, level, service, dan status." icon={FileText}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
            placeholder="Cari pesan..."
            aria-label="Cari pesan log"
            className="h-10 rounded-lg border border-[#e5e5e5] px-3 text-sm outline-none focus:border-forest/50"
          />
          <select
            value={level}
            onChange={(event) => {
              setLevel(event.target.value);
              setOffset(0);
            }}
            aria-label="Filter level"
            className="h-10 rounded-lg border border-[#e5e5e5] bg-white px-3 text-sm"
          >
            {LOG_LEVELS.map((value) => (
              <option key={value} value={value}>
                {value === "" ? "Semua level" : value}
              </option>
            ))}
          </select>
          <input
            value={service}
            onChange={(event) => {
              setService(event.target.value);
              setOffset(0);
            }}
            placeholder="Service (mis. api)"
            aria-label="Filter service"
            className="h-10 rounded-lg border border-[#e5e5e5] px-3 text-sm outline-none focus:border-forest/50"
          />
          <select
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setOffset(0);
            }}
            aria-label="Filter status"
            className="h-10 rounded-lg border border-[#e5e5e5] bg-white px-3 text-sm"
          >
            {LOG_STATUS.map((value) => (
              <option key={value} value={value}>
                {value === "" ? "Semua status" : value}
              </option>
            ))}
          </select>
        </div>
      </Card>
      <Card title={`Entries (${formatInt(total)})`} hint="Klik baris untuk detail." icon={Activity}>
        {loading ? (
          <Skeleton className="h-48 rounded-xl" />
        ) : entries.length > 0 ? (
          <>
            <ul className="divide-y divide-[#eef1ee]">
              {entries.map((log) => (
                <li key={log.log_id}>
                  <button
                    type="button"
                    className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2 text-left text-sm"
                    onClick={() => setDetail(detail?.log_id === log.log_id ? null : log)}
                    aria-expanded={detail?.log_id === log.log_id}
                  >
                    <span className="w-36 shrink-0 text-xs text-muted-text">{formatTime(log.timestamp)}</span>
                    <StatusBadge tone={log.level === "error" ? "danger" : log.level === "warn" ? "warning" : "neutral"}>
                      {log.level}
                    </StatusBadge>
                    <span className="font-mono text-tinta">{log.service}</span>
                    <span className="min-w-0 flex-1 truncate text-muted-text">{log.message}</span>
                  </button>
                  {detail?.log_id === log.log_id ? (
                    <dl className="grid grid-cols-1 gap-1 rounded-lg bg-[#f2f5f3] px-4 py-3 font-mono text-xs sm:grid-cols-2">
                      {(
                        [
                          ["request_id", log.request_id],
                          ["trace_id", log.trace_id],
                          ["route", log.route],
                          ["status", log.status_code],
                          ["duration_ms", log.duration_ms],
                          ["error_type", log.error_type],
                        ] as const
                      ).map(([key, value]) => (
                        <div key={key} className="flex gap-2">
                          <dt className="w-24 shrink-0 text-muted-text">{key}</dt>
                          <dd className="truncate text-tinta">{value ?? "—"}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                disabled={offset === 0 || fetching}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                className="h-9 rounded-lg border border-[#e5e5e5] px-4 text-sm font-semibold text-forest disabled:opacity-40"
              >
                Sebelumnya
              </button>
              <span className="inline-flex items-center gap-2 text-xs text-muted-text">
                {fetching ? <InlineSpinner label="Memuat halaman..." /> : null}
                {offset + 1}–{offset + entries.length} dari {formatInt(total)}
              </span>
              <button
                type="button"
                disabled={offset + entries.length >= total || fetching}
                onClick={() => setOffset(offset + limit)}
                className="h-9 rounded-lg border border-[#e5e5e5] px-4 text-sm font-semibold text-forest disabled:opacity-40"
              >
                Berikutnya
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-text">Tidak ada log pada filter ini.</p>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- traces

export function SystemTracesPage() {
  const [routeFilter, setRouteFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<SystemTraceDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingTraceId, setLoadingTraceId] = useState<string | null>(null);
  const { data, loading, fetching, error, reload } = useAdminFetch<{
    entries: SystemTraceSummary[];
    total: number;
  }>(
    (signal) => fetchSystemTraces({ route: routeFilter, status: statusFilter }, signal),
    [routeFilter, statusFilter]
  );

  async function openTrace(traceId: string) {
    if (selected?.trace_id === traceId) {
      setSelected(null);
      return;
    }
    setDetailError(null);
    setLoadingTraceId(traceId);
    try {
      const detail = await fetchSystemTrace(traceId);
      setSelected(detail);
    } catch (err) {
      setDetailError((err as Error).message);
    } finally {
      setLoadingTraceId(null);
    }
  }

  if (error) return <LoadError message={error} onRetry={reload} />;
  const entries = data?.entries ?? [];

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="System Monitoring"
        title="Traces"
        description="Error, timeout, lambat (>2 dtk), dan 5% sampel. Span lambat/error disorot."
        actions={
          <div className="flex items-center gap-2">
            {fetching ? <InlineSpinner label="Memuat traces..." /> : null}
            <button type="button" className={styles.upload} onClick={reload} disabled={fetching}>
              <RefreshCw className={cn("size-4", fetching && "animate-spin motion-reduce:animate-none")} strokeWidth={2} /> Muat ulang
            </button>
          </div>
        }
      />
      <Card title="Filter" hint="Route dan status trace." icon={Workflow}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            value={routeFilter}
            onChange={(event) => setRouteFilter(event.target.value)}
            placeholder="Route (mis. /chat/ask)"
            aria-label="Filter route"
            className="h-10 rounded-lg border border-[#e5e5e5] px-3 text-sm outline-none focus:border-forest/50"
          />
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter status"
            className="h-10 rounded-lg border border-[#e5e5e5] bg-white px-3 text-sm"
          >
            {["", "ok", "error", "timeout"].map((value) => (
              <option key={value} value={value}>
                {value === "" ? "Semua status" : value}
              </option>
            ))}
          </select>
        </div>
      </Card>
      <Card title={`Traces (${formatInt(data?.total ?? 0)})`} hint="Klik baris untuk waterfall." icon={Gauge}>
        {loading ? (
          <Skeleton className="h-48 rounded-xl" />
        ) : entries.length > 0 ? (
          <ul className="divide-y divide-[#eef1ee]">
            {entries.map((trace) => (
              <li key={trace.trace_id}>
                <button
                  type="button"
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2 text-left text-sm"
                  onClick={() => void openTrace(trace.trace_id)}
                  aria-expanded={selected?.trace_id === trace.trace_id}
                >
                  <span className="w-36 shrink-0 text-xs text-muted-text">{formatTime(trace.timestamp)}</span>
                  <StatusBadge tone={trace.status === "ok" ? "success" : "danger"}>{trace.status}</StatusBadge>
                  <span className="min-w-0 flex-1 truncate font-mono text-tinta">{trace.route}</span>
                  {loadingTraceId === trace.trace_id ? (
                    <InlineSpinner label="Memuat detail trace..." />
                  ) : null}
                  <span className="font-mono text-xs text-muted-text">{trace.span_count} span</span>
                  <span className="font-mono text-sm font-semibold text-tinta tabular-nums">
                    {formatMs(trace.duration_ms)}
                  </span>
                </button>
                {selected?.trace_id === trace.trace_id ? (
                  <TraceWaterfall detail={selected} />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-text">Tidak ada trace pada filter ini.</p>
        )}
        {detailError ? <p className="text-sm text-red">{detailError}</p> : null}
      </Card>
    </div>
  );
}

function TraceWaterfall({ detail }: { detail: SystemTraceDetail }) {
  const total = Math.max(1, detail.duration_ms);
  const roots = detail.spans.filter((span) => span.parent_span_id === null);
  const childrenOf = (spanId: string) =>
    detail.spans.filter((span) => span.parent_span_id === spanId);
  function renderSpan(span: (typeof detail.spans)[number], depth: number): ReactNode {
    const slow = (span.duration_ms ?? 0) > 1000;
    const failed = span.status !== "ok" && span.status !== "running";
    return (
      <div key={span.span_id}>
        <div className="flex items-center gap-2 py-1" style={{ paddingLeft: depth * 16 }}>
          <span className="w-32 shrink-0 truncate font-mono text-xs text-tinta">{span.name}</span>
          <div className="h-3 min-w-0 flex-1 overflow-hidden rounded-full bg-[#e9edea]">
            <div
              className={cn("h-full rounded-full", failed ? "bg-red" : slow ? "bg-amber" : "bg-forest")}
              style={{
                marginLeft: `${Math.min(100, ((span.started_offset_ms ?? 0) / total) * 100)}%`,
                width: `${Math.max(2, Math.min(100, ((span.duration_ms ?? 0) / total) * 100))}%`,
              }}
            />
          </div>
          <span className="w-20 shrink-0 text-right font-mono text-xs text-muted-text tabular-nums">
            {formatMs(span.duration_ms)}
          </span>
        </div>
        {span.error ? (
          <p className="text-xs text-red" style={{ paddingLeft: depth * 16 + 136 }}>
            {span.error}
          </p>
        ) : null}
        {childrenOf(span.span_id).map((child) => renderSpan(child, depth + 1))}
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-[#f2f5f3] px-4 py-3">
      <p className="mb-2 font-mono text-xs text-muted-text">
        {detail.trace_id} · total {formatMs(detail.duration_ms)}
      </p>
      {roots.length > 0 ? (
        roots.map((span) => renderSpan(span, 0))
      ) : (
        detail.spans.map((span) => renderSpan(span, 0))
      )}
    </div>
  );
}

// ---------------------------------------------------------------- alerts

export function SystemAlertsPage() {
  const { data, loading, fetching, error, reload } = useAdminFetch<{
    rules: AlertRule[];
    active: { rule: string; severity: string; message: string }[];
    recent: AlertEvent[];
  }>((signal) => fetchSystemAlerts(signal));

  if (loading) {
    return (
      <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`} role="status" aria-label="Memuat alerts">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }
  if (error || !data) return <LoadError message={error ?? "Coba muat ulang."} onRetry={reload} />;
  const activeRules = new Set(data.active.map((alert) => alert.rule));

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="System Monitoring"
        title="Alerts"
        description="Aturan berbasis kode dievaluasi tiap dibaca. Tanpa integrasi notifikasi eksternal."
        actions={
          <div className="flex items-center gap-2">
            {fetching ? <InlineSpinner label="Memuat alerts..." /> : null}
            <button type="button" className={styles.upload} onClick={reload} disabled={fetching}>
              <RefreshCw className={cn("size-4", fetching && "animate-spin motion-reduce:animate-none")} strokeWidth={2} /> Muat ulang
            </button>
          </div>
        }
      />
      <Card title="Alert Rules" hint="Firing aktif disorot." icon={Bell}>
        <ul className="space-y-2">
          {data.rules.map((rule) => (
            <li key={rule.rule} className="flex items-center gap-2 text-sm">
              <StatusBadge tone={rule.severity === "critical" ? "danger" : "warning"}>
                {rule.severity}
              </StatusBadge>
              <span className="font-mono text-tinta">{rule.rule}</span>
              <span className="min-w-0 flex-1 truncate text-muted-text">{rule.description}</span>
              {activeRules.has(rule.rule) ? (
                <StatusBadge tone="danger">firing</StatusBadge>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Recent Events" hint="20 event terakhir, firing dan resolved." icon={Monitor}>
        {data.recent.length > 0 ? (
          <ul className="divide-y divide-[#eef1ee]">
            {data.recent.map((event) => (
              <li key={event.alert_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className="w-36 shrink-0 text-xs text-muted-text">{formatTime(event.created_at)}</span>
                <StatusBadge tone={event.status === "firing" ? "danger" : "success"}>
                  {event.status}
                </StatusBadge>
                <span className="font-mono text-tinta">{event.rule}</span>
                <span className="min-w-0 flex-1 truncate text-muted-text">{event.message}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-text">Belum ada alert event.</p>
        )}
      </Card>
    </div>
  );
}
