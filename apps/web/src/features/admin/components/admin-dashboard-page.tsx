"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { AlertIcon, DatabaseIcon, ThumbsDownIcon, ThumbsUpIcon } from "@/components/icons";
import { ArrowDown, ArrowRight, ArrowUp, BarChart3, ChevronRight, CircleCheck, Crosshair, Database, FileUp, HeartPulse, Layers, Pencil, ScrollText, MessagesSquare, ShieldCheck, Timer, Trash2, TrendingUp, TriangleAlert, Users } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  clearStoredSession,
  fetchAdminMetrics,
  fetchAdminStats,
  fetchRecentAuditLogs,
  fetchDailyUsage,
  fetchEvaluationRuns,
} from "@/features/admin/api";
import type {
  AdminMetrics,
  AdminStats,
  AuditLogEntry,
  DailyUsagePoint,
  EvaluationMetricSet,
  EvaluationRunSummary,
} from "@/features/admin/types";
import { cn } from "@/lib/utils";
import styles from "./admin-dashboard.module.css";

const ingestionTone: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  completed: "success",
  needs_review: "warning",
  failed: "danger",
  running: "info",
  queued: "neutral",
};

const ingestionLabel: Record<string, string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDate(value: string) {
  const d = safeDate(value);
  if (!d) return "Tidak diketahui";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function formatRelative(value: string) {
  const d = safeDate(value);
  if (!d) return "Tidak diketahui";
  const minutes = Math.round((Date.now() - d.getTime()) / 60000);
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} hari lalu`;
  return formatDate(value);
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const width = 96;
  const height = 32;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const coords = points.map((value, index) => {
    const x = (index / (points.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className="h-8 w-20 shrink-0 text-forest sm:w-24"
    >
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const TREND_COLORS = {
  messages: "#23864b",
  conversations: "#2f7fd1",
  active_users: "#b7791f",
} as const;

function niceCeil(value: number) {
  if (value <= 4) return 4;
  const power = 10 ** Math.floor(Math.log10(value));
  const scaled = value / power;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 2.5 ? 2.5 : scaled <= 5 ? 5 : 10;
  return nice * power;
}

function shortDay(isoDate: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

function UsageTrendChart({ points }: { points: DailyUsagePoint[] }) {
  const width = 640;
  const height = 280;
  const padLeft = 36;
  const padRight = 8;
  const padTop = 12;
  const padBottom = 26;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const maxValue = niceCeil(
    Math.max(1, ...points.map((p) => Math.max(p.messages, p.conversations, p.active_users)))
  );
  const xAt = (index: number) =>
    points.length <= 1
      ? padLeft + plotW / 2
      : padLeft + (index / (points.length - 1)) * plotW;
  const yAt = (value: number) => padTop + (1 - value / maxValue) * plotH;
  const line = (pick: (point: DailyUsagePoint) => number) =>
    points.map((point, index) => `${xAt(index).toFixed(1)},${yAt(pick(point)).toFixed(1)}`).join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => Math.round(fraction * maxValue));
  const seriesOrder = (
    [
      {
        key: "messages",
        color: TREND_COLORS.messages,
        pick: (p: DailyUsagePoint) => p.messages,
      },
      {
        key: "conversations",
        color: TREND_COLORS.conversations,
        pick: (p: DailyUsagePoint) => p.conversations,
      },
      {
        key: "active_users",
        color: TREND_COLORS.active_users,
        pick: (p: DailyUsagePoint) => p.active_users,
      },
    ] as const
  )
    .map((series) => ({
      ...series,
      max: Math.max(0, ...points.map(series.pick)),
    }))
    .sort((a, b) => b.max - a.max);
  const labelIndexes =
    points.length <= 6
      ? points.map((_, index) => index)
      : Array.from({ length: 6 }, (_, k) => Math.round((k * (points.length - 1)) / 5));
  const totals = points.reduce(
    (acc, point) => ({
      messages: acc.messages + point.messages,
      conversations: acc.conversations + point.conversations,
      activeUsers: acc.activeUsers + point.active_users,
    }),
    { messages: 0, conversations: 0, activeUsers: 0 }
  );
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Tren 30 hari: ${totals.messages} pertanyaan, ${totals.conversations} percakapan, ${totals.activeUsers} pengguna aktif.`}
      className="block h-[300px] w-full"
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={padLeft}
            x2={width - padRight}
            y1={yAt(tick)}
            y2={yAt(tick)}
            stroke="#e5e5e5"
            strokeWidth="1"
          />
          <text x={padLeft - 8} y={yAt(tick) + 3.5} textAnchor="end" fontSize="10" fill="#607067">
            {tick}
          </text>
        </g>
      ))}
      {labelIndexes.map((index) => (
        <text
          key={points[index].date}
          x={xAt(index)}
          y={height - 8}
          textAnchor="middle"
          fontSize="10"
          fill="#607067"
        >
          {shortDay(points[index].date)}
        </text>
      ))}
      {seriesOrder.map((series) => (
        <polyline
          key={series.key}
          points={line(series.pick)}
          fill="none"
          stroke={series.color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}

function KnowledgeDonut({
  segments,
  total,
}: {
  segments: { label: string; value: number; color: string }[];
  total: number;
}) {
  const size = 176;
  const stroke = 24;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const visible = segments.filter((segment) => segment.value > 0 && total > 0);
  const arcs = visible.map((segment, index) => {
    const length = (segment.value / total) * circumference;
    const offset = visible
      .slice(0, index)
      .reduce((sum, prev) => sum + (prev.value / total) * circumference, 0);
    return { ...segment, dash: `${length} ${circumference - length}`, offset: -offset };
  });
  return (
    <div className="relative mx-auto size-44">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`Komposisi dokumen: ${segments.map((s) => `${s.label} ${s.value}`).join(", ")}`}
        className="size-full -rotate-90"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#eef1ee"
          strokeWidth={stroke}
        />
        {arcs.map((arc) => (
          <circle
            key={arc.label}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={arc.color}
            strokeWidth={stroke}
            strokeDasharray={arc.dash}
            strokeDashoffset={arc.offset}
          />
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="font-mono text-3xl leading-none font-bold tracking-tight text-forest tabular-nums">
          {new Intl.NumberFormat("id-ID").format(total)}
        </p>
        <p className="mt-1 text-xs text-muted-text">Total Dokumen</p>
      </div>
    </div>
  );
}

function auditIcon(action: string) {
  if (action === "document.uploaded") return FileUp;
  if (action === "document.published") return CircleCheck;
  if (action === "document.metadata_updated" || action === "document.relationships_updated")
    return Pencil;
  if (action.endsWith("_verification")) return ShieldCheck;
  if (action.startsWith("ingestion_build.")) return Layers;
  if (action === "chat_purge") return Trash2;
  return ScrollText;
}

function verificationResult(details: Record<string, unknown>) {
  const status = details.status;
  if (status === "verified") return "terverifikasi";
  if (status === "rejected") return "ditolak";
  if (status === "pending") return "menunggu keputusan";
  return typeof status === "string" && status ? status : "diperbarui";
}

function describeAudit(entry: AuditLogEntry) {
  const target = entry.target_id ?? "";
  const details = entry.details ?? {};
  const fileName = typeof details.file_name === "string" && details.file_name ? details.file_name : target;
  switch (entry.action) {
    case "document.uploaded":
      return `Upload dokumen "${fileName}"`;
    case "document.published":
      return `Publish dokumen ${target}`;
    case "document.draft":
      return `Batal terbit dokumen ${target} (kembali ke draft)`;
    case "document.metadata_updated":
      return `Metadata dokumen ${target} diperbarui`;
    case "document.relationships_updated":
      return `Relasi dokumen ${target} diperbarui`;
    case "document.source_verification":
      return `Verifikasi sumber dokumen ${target} ${verificationResult(details)}`;
    case "document.legal_verification":
      return `Review hukum dokumen ${target} ${verificationResult(details)}`;
    case "ingestion_build.approved":
      return `Setujui hasil ingestion ${target}`;
    case "ingestion_build.rejected":
      return `Tolak hasil ingestion ${target}`;
    case "prompt_create":
      return `Buat versi prompt ${target}`;
    case "prompt_publish":
      return `Publish versi prompt ${target}`;
    case "chat_purge":
      return "Bersihkan percakapan lama";
    default:
      if (entry.action.startsWith("document.") && entry.action.endsWith("_verification"))
        return `Verifikasi dokumen ${target}`;
      if (entry.action.startsWith("ingestion_build."))
        return `Review ingestion ${target}`;
      if (entry.action.startsWith("document.")) return `Dokumen ${target} diperbarui`;
      return entry.action;
  }
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-44" />
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[104px] rounded-xl" />
        ))}
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-52" />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[104px] rounded-xl" />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Skeleton className="h-72 rounded-xl lg:col-span-3" />
        <Skeleton className="h-72 rounded-xl lg:col-span-2" />
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-64 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-56 rounded-xl" />
    </div>
  );
}

export function AdminDashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvaluationRunSummary[] | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsagePoint[] | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const inFlightRef = useRef(false);
  const lastUpdatedRef = useRef<number | null>(null);

  const applyStats = useCallback((data: AdminStats) => {
    setStats(data);
    setError(null);
    setLastUpdated(Date.now());
    lastUpdatedRef.current = Date.now();
  }, []);

  const handleAuthError = useCallback(() => {
    clearStoredSession();
    router.push("/login-admin");
  }, [router]);

  function isAuthError(message: string) {
    return message === "Invalid or expired token." || message === "Missing bearer token.";
  }

  const loadFull = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const [freshStats, freshMetrics, freshRuns, freshDaily, freshAudit] = await Promise.all([
          fetchAdminStats(signal),
          fetchAdminMetrics(signal).catch(() => null),
          fetchEvaluationRuns(signal).catch(() => null),
          fetchDailyUsage(30, signal).catch(() => null),
          fetchRecentAuditLogs(5, signal).catch(() => null),
        ]);
        applyStats(freshStats);
        setMetrics(freshMetrics);
        setEvalRuns(freshRuns);
        setDailyUsage(freshDaily?.points ?? null);
        setAuditLogs(freshAudit);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "Gagal memuat data dashboard.";
        if (isAuthError(message)) {
          handleAuthError();
          return;
        }
        setError(message);
      } finally {
        setLoading(false);
      }
    },
    [applyStats, handleAuthError]
  );

  const refreshSilent = useCallback(async () => {
    if (inFlightRef.current || document.hidden) return;
    inFlightRef.current = true;
    try {
      const [freshStats, freshMetrics, freshRuns, freshDaily, freshAudit] = await Promise.all([
        fetchAdminStats(),
        fetchAdminMetrics().catch(() => null),
        fetchEvaluationRuns().catch(() => null),
        fetchDailyUsage(30).catch(() => null),
        fetchRecentAuditLogs(5).catch(() => null),
      ]);
      applyStats(freshStats);
      if (freshMetrics) setMetrics(freshMetrics);
      if (freshRuns) setEvalRuns(freshRuns);
      if (freshDaily) setDailyUsage(freshDaily.points);
      if (freshAudit) setAuditLogs(freshAudit);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const message = (err as Error).message || "";
      if (isAuthError(message)) {
        handleAuthError();
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [applyStats, handleAuthError]);

  const refreshIfStale = useCallback(() => {
    const last = lastUpdatedRef.current;
    if (last !== null && Date.now() - last < 55000) return;
    void refreshSilent();
  }, [refreshSilent]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadFull(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadFull]);

  useEffect(() => {
    function handleVisibilityChange() {
      if (!document.hidden) refreshIfStale();
    }
    const id = window.setInterval(refreshIfStale, 60000);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refreshIfStale]);

  if (loading) {
    return (
      <div
        className={`${styles.dashboard} mx-auto max-w-[1200px]`}
        role="status"
        aria-label="Memuat dashboard"
      >
        <DashboardSkeleton />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className={`${styles.dashboard} flex min-h-64 items-center justify-center`} role="alert">
        <div className="w-full max-w-sm rounded-xl border border-[#e5e5e5] bg-white p-2 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <EmptyState
            icon={AlertIcon}
            title="Data dashboard tidak dapat dimuat"
            hint={error ?? "Coba muat ulang halaman."}
            action={
              <button
                type="button"
                className="h-11 rounded-xl border border-[#e5e5e5] bg-white px-5 text-sm font-semibold text-forest transition hover:border-forest hover:text-teal"
                onClick={() => {
                  void loadFull();
                }}
              >
                Muat ulang
              </button>
            }
          />
        </div>
      </div>
    );
  }

  const docPercent =
    stats.documents.total > 0
      ? Math.round((stats.documents.published / stats.documents.total) * 100)
      : 0;

  const kpiValues: Record<string, number> = {
    documents: stats.documents.total,
    published: stats.documents.published,
    users: stats.users,
    messages: stats.messages,
  };
  const reviewPending = stats.documents.needs_review;
  const failedDocs = stats.documents.failed;
  const kpiFooters: { text: string }[] = [
    { text: `${docPercent}% telah diterbitkan` },
    {
      text: reviewPending > 0 ? `${reviewPending} menunggu review` : "Tidak ada antrean",
    },
    { text: `${stats.conversations} percakapan aktif` },
    { text: `${stats.feedback.total} feedback masuk` },
  ];
  const kpiCards = [
    { key: "documents", label: "Total dokumen", icon: ScrollText },
    { key: "published", label: "Dokumen terbit", icon: Database },
    { key: "users", label: "Pengguna terdaftar", icon: Users },
    { key: "messages", label: "Total pesan", icon: MessagesSquare },
  ] as const;

  const hasTotal = stats.documents.total > 0;
  const kbProcessing = Math.max(
    0,
    stats.documents.total - stats.documents.published - reviewPending - failedDocs
  );
  const kbSegments = [
    { label: "Selesai", value: stats.documents.published, color: "#23864b" },
    { label: "Perlu review", value: reviewPending, color: "#b7791f" },
    { label: "Diproses", value: kbProcessing, color: "#2f7fd1" },
    { label: "Gagal", value: failedDocs, color: "#c0392b" },
  ];
  const kbReadyPct = hasTotal
    ? Math.round((stats.documents.published / stats.documents.total) * 100)
    : 0;
  const trendPoints = dailyUsage ?? [];
  const trendHasActivity = trendPoints.some(
    (point) => point.messages > 0 || point.conversations > 0 || point.active_users > 0
  );

  const satisfaction =
    stats.feedback.total > 0
      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
      : 0;

  const completedRuns = (evalRuns ?? [])
    .filter((run) => run.status === "completed")
    .sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));
  const latestCompletedRun = completedRuns[completedRuns.length - 1] ?? null;
  function bestModeMetrics(run: EvaluationRunSummary) {
    let best: { key: string; metrics: EvaluationMetricSet } | null = null;
    for (const [key, metrics] of Object.entries(run.metrics)) {
      if (!best || metrics.recall_at_5 > best.metrics.recall_at_5)
        best = { key, metrics };
    }
    return best;
  }
  function prettyMode(key: string) {
    return key.charAt(0).toUpperCase() + key.slice(1);
  }
  const latestBest = latestCompletedRun ? bestModeMetrics(latestCompletedRun) : null;
  const latestBestLabel = latestBest
    ? `${prettyMode(latestBest.key)} · ${shortDay(latestCompletedRun.created_at.slice(0, 10))}`
    : "Belum ada evaluasi selesai";
  const recallAt5 = latestBest?.metrics.recall_at_5 ?? null;
  const mrr = latestBest?.metrics.mean_reciprocal_rank ?? null;
  const bestSeries = completedRuns
    .map((run) => bestModeMetrics(run)?.metrics ?? null)
    .filter((metrics): metrics is EvaluationMetricSet => metrics !== null);
  const recallSeries = bestSeries.map((metrics) => metrics.recall_at_5);
  const mrrSeries = bestSeries.map((metrics) => metrics.mean_reciprocal_rank);
  const recallDelta =
    recallSeries.length >= 2
      ? recallSeries[recallSeries.length - 1] - recallSeries[recallSeries.length - 2]
      : null;
  const mrrDelta =
    mrrSeries.length >= 2
      ? mrrSeries[mrrSeries.length - 1] - mrrSeries[mrrSeries.length - 2]
      : null;
  const avgLatency =
    metrics?.request_latency?.avg ?? metrics?.request_latency?.p50 ?? null;
  const requestTotal = metrics?.requests.total ?? 0;
  const providerErrorTotal = metrics?.provider_errors.last_7_days ?? 0;
  const hasHealthSignal =
    stats.messages > 0 || requestTotal > 0 || latestCompletedRun !== null;
  const health: "healthy" | "attention" | "nodata" = !hasHealthSignal
    ? "nodata"
    : providerErrorTotal > 0
      ? "attention"
      : "healthy";
  const healthUpdatedLabel =
    lastUpdated === null
      ? "Belum pernah diperbarui"
      : `Terakhir diperbarui: ${new Intl.DateTimeFormat("id-ID", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Jakarta",
        }).format(new Date(lastUpdated))} WIB`;
  const healthCards = [
    {
      key: "recall",
      label: "Recall@5",
      icon: Crosshair,
      display: recallAt5 === null ? "N/A" : `${(recallAt5 * 100).toFixed(1)}%`,
      hint: latestBestLabel,
      delta: recallDelta === null ? null : recallDelta * 100,
      deltaSuffix: "%",
      series: recallSeries,
    },
    {
      key: "mrr",
      label: "MRR",
      icon: BarChart3,
      display: mrr === null ? "N/A" : `${(mrr * 100).toFixed(1)}%`,
      hint: latestBestLabel,
      delta: mrrDelta === null ? null : mrrDelta * 100,
      deltaSuffix: "%",
      series: mrrSeries,
    },
    {
      key: "helpful",
      label: "Helpful Rate",
      icon: ThumbsUpIcon,
      display: stats.feedback.total > 0 ? `${satisfaction}%` : "N/A",
      hint:
        stats.feedback.total > 0
          ? `${stats.feedback.total} penilaian pengguna`
          : "Belum ada feedback",
      delta: null,
      deltaSuffix: "",
      series: [],
    },
    {
      key: "latency",
      label: "Avg Latency",
      icon: Timer,
      display: avgLatency === null ? "N/A" : `${avgLatency.toFixed(1)}s`,
      hint: requestTotal > 0 ? `${requestTotal} permintaan` : "Belum ada permintaan",
      delta: null,
      deltaSuffix: "",
      series: [],
    },
  ] as const;

  const belowTargetEvals = completedRuns.filter((run) => {
    const best = bestModeMetrics(run);
    return best !== null && best.metrics.recall_at_5 < 0.8;
  }).length;
  const alerts: { key: string; count: number; text: string; tone: string; href: string }[] = [];
  if (failedDocs > 0)
    alerts.push({
      key: "failed",
      count: failedDocs,
      text: "dokumen gagal diproses",
      tone: "text-red",
      href: "/documents",
    });
  if (belowTargetEvals > 0)
    alerts.push({
      key: "evals",
      count: belowTargetEvals,
      text: "evaluasi retrieval di bawah target",
      tone: "text-red",
      href: "/admin/evaluation",
    });
  if (reviewPending > 0)
    alerts.push({
      key: "review",
      count: reviewPending,
      text: "dokumen menunggu review",
      tone: "text-amber",
      href: "/documents",
    });

  const attentionParts: string[] = [];
  if (reviewPending > 0) attentionParts.push(`${reviewPending} dokumen menunggu tinjauan`);
  if (failedDocs > 0) attentionParts.push(`${failedDocs} gagal diproses`);

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="Ikhtisar operasional"
        title="Dashboard"
        description="Ringkasan dokumen, percakapan, dan feedback pengguna."
        actions={
          <Link href="/admin/upload" className={styles.upload}>
            <FileUp className="size-4" strokeWidth={2} /> Upload dokumen
          </Link>
        }
      />

      {attentionParts.length > 0 ? (
        <Link
          href="/documents"
          className={cn(
            "group flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 transition",
            failedDocs > 0
              ? "border-red/30 bg-red-soft hover:border-red/60"
              : "border-amber/30 bg-amber-soft hover:border-amber/60"
          )}
        >
          <AlertIcon
            className={cn("size-5 shrink-0", failedDocs > 0 ? "text-red" : "text-amber")}
          />
          <p className="min-w-0 flex-1 text-sm text-tinta">
            <strong className="font-semibold">{attentionParts.join(" dan ")}</strong>.
          </p>
          <span
            className={cn(
              "shrink-0 text-xs font-semibold group-hover:underline",
              failedDocs > 0 ? "text-red" : "text-amber"
            )}
          >
            Tinjau sekarang
          </span>
        </Link>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card, index) => {
          const Icon = card.icon;
          const foot = kpiFooters[index];
          return (
            <div
              key={card.key}
              className="rounded-xl border border-[#e5e5e5] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(27,67,50,0.06)]"
            >
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                  <Icon strokeWidth={1.75} className="size-5 text-forest" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-text">{card.label}</p>
                  <p className="mt-0.5 font-mono text-[26px] leading-none font-bold tracking-tight whitespace-nowrap text-tinta tabular-nums">
                    {new Intl.NumberFormat("id-ID").format(kpiValues[card.key])}
                  </p>
                  <p className="mt-1 truncate text-[11px] text-muted-text">{foot.text}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <section aria-label="Kesehatan RAG">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
              <HeartPulse aria-hidden="true" className="size-4 text-forest" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-forest">RAG Health</h2>
              <p className="mt-1 text-xs text-muted-text">
                Metrik utama sistem RAG untuk memantau kualitas dan performa.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {health === "healthy" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-teal-soft px-3 py-1 text-xs font-semibold text-forest">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-forest" />
                Healthy
              </span>
            ) : health === "attention" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-soft px-3 py-1 text-xs font-semibold text-amber">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-amber" />
                Perlu perhatian
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-soft px-3 py-1 text-xs font-semibold text-muted-text">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-muted-text" />
                Belum ada data
              </span>
            )}
            <span className="text-xs text-muted-text tabular-nums">{healthUpdatedLabel}</span>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {healthCards.map((card) => {
            const Icon = card.icon;
            const TrendIcon = card.delta === null ? null : card.delta >= 0 ? ArrowUp : ArrowDown;
            return (
              <div
                key={card.key}
                className="rounded-xl border border-[#e5e5e5] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(27,67,50,0.06)]"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                    <Icon className="size-5 text-forest" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-muted-text">{card.label}</p>
                    <div className="mt-0.5 flex items-baseline gap-2">
                      <p className="font-mono text-[26px] leading-none font-bold tracking-tight whitespace-nowrap text-tinta tabular-nums">
                        {card.display}
                      </p>
                      {TrendIcon && card.delta !== null ? (
                        <span
                          className={cn(
                            "inline-flex shrink-0 items-center gap-0.5 text-[11px] font-semibold tabular-nums",
                            card.delta >= 0 ? "text-forest" : "text-red"
                          )}
                        >
                          <TrendIcon aria-hidden="true" className="size-3" />
                          {card.delta >= 0 ? "+" : ""}
                          {card.delta.toFixed(card.deltaSuffix ? 1 : 3)}
                          {card.deltaSuffix}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-text">{card.hint}</p>
                  </div>
                  <Sparkline points={[...card.series]} />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="flex flex-col overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)] lg:col-span-3">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e5e5e5] px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                <TrendingUp aria-hidden="true" className="size-4 text-forest" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-forest">Tren Penggunaan (30 Hari)</h2>
                <p className="mt-0.5 text-xs text-muted-text">
                  Aktivitas pertanyaan, percakapan, dan pengguna dalam 30 hari terakhir.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs text-muted-text">
              <span className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: TREND_COLORS.messages }}
                />
                Pertanyaan
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: TREND_COLORS.conversations }}
                />
                Percakapan
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: TREND_COLORS.active_users }}
                />
                Pengguna aktif
              </span>
            </div>
          </header>
          <div className="flex flex-1 flex-col justify-center px-6 py-5">
            {dailyUsage === null ? (
              <p className="rounded-lg border border-dashed border-[#e5e5e5] px-4 py-10 text-center text-sm text-muted-text">
                Data tren belum dapat dimuat. Coba muat ulang halaman.
              </p>
            ) : trendHasActivity ? (
              <UsageTrendChart points={trendPoints} />
            ) : (
              <p className="rounded-lg border border-dashed border-[#e5e5e5] px-4 py-10 text-center text-sm text-muted-text">
                Belum ada aktivitas dalam 30 hari terakhir.
              </p>
            )}
          </div>
        </section>

        <section className="flex flex-col overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)] lg:col-span-2">
          <header className="flex items-center justify-between border-b border-[#e5e5e5] px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                <Database aria-hidden="true" className="size-4 text-forest" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-forest">Kondisi Knowledge Base</h2>
                <p className="mt-0.5 text-xs text-muted-text">
                  Status pemrosesan seluruh dokumen dalam sistem.
                </p>
              </div>
            </div>
            <Link
              href="/documents"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-3.5 -my-3 -mr-2 text-xs font-semibold text-forest transition hover:text-teal"
            >
              Kelola dokumen
              <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
          </header>
          <div className="flex flex-1 flex-col justify-center px-6 py-5">
            {hasTotal ? (
              <>
                <KnowledgeDonut segments={kbSegments} total={stats.documents.total} />
                <ul className="mt-5 space-y-2.5">
                  {kbSegments.map((segment) => (
                    <li key={segment.label} className="flex items-center gap-2.5">
                      <span
                        aria-hidden="true"
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: segment.color }}
                      />
                      <span className="flex-1 text-sm text-muted-text">{segment.label}</span>
                      <span className="font-mono text-sm font-semibold text-tinta tabular-nums">
                        {new Intl.NumberFormat("id-ID").format(segment.value)}
                      </span>
                      <span className="w-10 shrink-0 text-right text-xs text-muted-text tabular-nums">
                        {Math.round((segment.value / stats.documents.total) * 100)}%
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 flex items-center gap-2 rounded-lg bg-teal-soft/60 px-4 py-2.5 text-xs font-medium text-forest">
                  <CircleCheck aria-hidden="true" className="size-4 shrink-0" />
                  {kbReadyPct}% dokumen siap menjawab pertanyaan pengguna.
                </p>
              </>
            ) : (
              <p className="rounded-lg border border-dashed border-[#e5e5e5] px-4 py-6 text-center text-sm text-muted-text">
                Belum ada dokumen di basis pengetahuan.{" "}
                <Link
                  href="/admin/upload"
                  className="font-semibold text-forest underline underline-offset-2 transition hover:text-teal"
                >
                  Unggah PDF pertama
                </Link>{" "}
                untuk memulai.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <header className="border-b border-[#e5e5e5] px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                <MessagesSquare aria-hidden="true" className="size-4 text-forest" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-forest">Feedback Pengguna</h2>
                <p className="mt-0.5 text-xs text-muted-text">
                  Penilaian pengguna terhadap jawaban AI.
                </p>
              </div>
            </div>
          </header>
          <div className="px-6 py-5">
            {stats.feedback.total > 0 ? (
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between gap-3">
                    <p className="inline-flex items-center gap-2 text-sm text-muted-text">
                      <ThumbsUpIcon aria-hidden="true" className="size-4 text-forest" />
                      Helpful
                    </p>
                    <p className="font-mono text-sm font-semibold text-tinta tabular-nums">
                      {stats.feedback.helpful}
                      <span className="ml-2 text-xs font-normal text-muted-text">
                        {satisfaction}%
                      </span>
                    </p>
                  </div>
                  <div
                    role="img"
                    aria-label={`${satisfaction}% feedback menilai membantu`}
                    className="mt-2 h-2.5 overflow-hidden rounded-full bg-[#e9edea]"
                  >
                    <div className="h-full rounded-full bg-forest" style={{ width: `${satisfaction}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between gap-3">
                    <p className="inline-flex items-center gap-2 text-sm text-muted-text">
                      <ThumbsDownIcon aria-hidden="true" className="size-4 text-red" />
                      Tidak membantu
                    </p>
                    <p className="font-mono text-sm font-semibold text-tinta tabular-nums">
                      {stats.feedback.not_helpful}
                      <span className="ml-2 text-xs font-normal text-muted-text">
                        {100 - satisfaction}%
                      </span>
                    </p>
                  </div>
                  <div
                    role="img"
                    aria-label={`${100 - satisfaction}% feedback menilai tidak membantu`}
                    className="mt-2 h-2.5 overflow-hidden rounded-full bg-[#e9edea]"
                  >
                    <div
                      className="h-full rounded-full bg-red"
                      style={{ width: `${100 - satisfaction}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-text">Belum ada feedback masuk dari pengguna.</p>
            )}
            <Link
              href="/admin/feedback"
              className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-forest transition hover:text-teal"
            >
              Lihat semua feedback
              <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
          </div>
        </section>

        <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <header className="border-b border-[#e5e5e5] px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                <Layers aria-hidden="true" className="size-4 text-forest" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-forest">Ingestion Terbaru</h2>
                <p className="mt-0.5 text-xs text-muted-text">Proses ingestion terakhir.</p>
              </div>
            </div>
          </header>
          {stats.ingestion_jobs.recent.length === 0 ? (
            <div className="px-6 py-5">
              <EmptyState
                icon={DatabaseIcon}
                title="Belum ada pemrosesan dokumen"
                hint="Unggah PDF pertama untuk mulai menyiapkan sumber jawaban."
              />
            </div>
          ) : (
            <>
              <ul className="divide-y divide-dashed divide-[#e5e5e5] px-3 py-2">
                {stats.ingestion_jobs.recent.slice(0, 4).map((job) => (
                  <li key={job.job_id}>
                    <Link
                      href="/admin/ingestion"
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-surface-soft"
                    >
                      <span
                        title={job.document_id}
                        className="min-w-0 flex-1 truncate text-sm font-medium text-tinta"
                      >
                        {job.document_id}
                      </span>
                      <StatusBadge tone={ingestionTone[job.status] ?? "neutral"}>
                        {ingestionLabel[job.status] ?? job.status}
                      </StatusBadge>
                      <time
                        dateTime={job.created_at}
                        title={formatDate(job.created_at)}
                        className="w-20 shrink-0 text-right text-xs text-muted-text tabular-nums"
                      >
                        {formatRelative(job.created_at)}
                      </time>
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="px-6 pb-5">
                <Link
                  href="/admin/ingestion"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-forest transition hover:text-teal"
                >
                  Lihat semua ingestion
                  <ArrowRight aria-hidden="true" className="size-3.5" />
                </Link>
              </div>
            </>
          )}
        </section>

        <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <header className="border-b border-[#e5e5e5] px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-amber-soft">
                <TriangleAlert aria-hidden="true" className="size-4 text-amber" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-forest">Alert & Tindakan</h2>
                <p className="mt-0.5 text-xs text-muted-text">
                  Isu penting yang memerlukan perhatian.
                </p>
              </div>
            </div>
          </header>
          <div className="px-6 py-5">
            {alerts.length > 0 ? (
              <ul className="space-y-1">
                {alerts.map((alert) => (
                  <li key={alert.key}>
                    <Link
                      href={alert.href}
                      className="flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-surface-soft"
                    >
                      <AlertIcon className={cn("size-5 shrink-0", alert.tone)} />
                      <span className="flex-1 text-sm text-tinta">
                        <strong className="font-semibold tabular-nums">{alert.count}</strong>{" "}
                        {alert.text}
                      </span>
                      <ChevronRight
                        aria-hidden="true"
                        className="size-4 shrink-0 text-muted-text/50"
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-col items-center gap-2 rounded-lg bg-white px-4 py-6 text-center">
                <span className="flex size-10 items-center justify-center rounded-full bg-teal-soft">
                  <CircleCheck aria-hidden="true" className="size-5 text-forest" />
                </span>
                <p className="text-sm font-medium text-tinta">Semua aman</p>
                <p className="text-xs text-muted-text">
                  Tidak ada isu yang perlu perhatian saat ini.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
        <header className="border-b border-[#e5e5e5] px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
              <ScrollText aria-hidden="true" className="size-4 text-forest" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-forest">Aktivitas Sistem Terbaru</h2>
              <p className="mt-0.5 text-xs text-muted-text">Log aktivitas penting dalam sistem.</p>
            </div>
          </div>
        </header>
        {auditLogs === null ? (
          <p className="px-6 py-8 text-center text-sm text-muted-text">
            Data aktivitas belum dapat dimuat.
          </p>
        ) : auditLogs.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-muted-text">
            Belum ada aktivitas tercatat dalam sistem.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-[#e5e5e5] text-xs text-muted-text">
                  <th scope="col" className="px-6 py-3 font-medium">
                    Waktu
                  </th>
                  <th scope="col" className="px-3 py-3 font-medium">
                    Aktivitas
                  </th>
                  <th scope="col" className="px-3 py-3 font-medium">
                    User
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dashed divide-[#e5e5e5]">
                {auditLogs.map((entry) => {
                  const ActivityIcon = auditIcon(entry.action);
                  return (
                    <tr key={entry.audit_id}>
                      <td className="px-6 py-3 whitespace-nowrap text-xs text-muted-text tabular-nums">
                        <time dateTime={entry.created_at}>{formatDate(entry.created_at)}</time>
                      </td>
                      <td className="px-3 py-3">
                        <span className="flex items-start gap-2.5">
                          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                            <ActivityIcon aria-hidden="true" className="size-4 text-forest" />
                          </span>
                          <span className="min-w-0 flex-1 font-medium break-words text-tinta">
                            {describeAudit(entry)}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-3 text-xs whitespace-nowrap text-muted-text">
                        {entry.actor_name || entry.actor}
                      </td>
                      <td className="px-6 py-3 text-right">
                        <StatusBadge tone="success">Sukses</StatusBadge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
