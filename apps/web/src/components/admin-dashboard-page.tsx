"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Database,
  FileCheck2,
  FileText,
  FlaskConical,
  MessageSquare,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  Upload,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { clearStoredSession, fetchAdminStats } from "@/lib/api";
import type { AdminStats } from "@/lib/types";

const ingestionStatusLabel: Record<string, string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

const ingestionStatusBadge: Record<string, string> = {
  completed: "bg-teal-soft text-teal",
  needs_review: "bg-amber-soft text-amber",
  failed: "bg-red-soft text-red",
  running: "bg-muted text-muted-foreground",
  queued: "bg-muted text-muted-foreground",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function StatCard({
  icon: Icon,
  label,
  value,
  note,
  dotClass,
}: {
  icon: typeof FileText;
  label: string;
  value: number;
  note: string;
  dotClass: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-end justify-between gap-4">
        <p className="font-mono text-3xl font-semibold tracking-tight tabular-nums">{value}</p>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-soft text-teal">
          <Icon className="size-4" />
        </span>
      </CardContent>
      <div className="flex items-center gap-1.5 border-t px-(--card-spacing) py-3">
        <span className={cn("size-1.5 rounded-full", dotClass)} />
        <span className="text-xs text-muted-foreground">{note}</span>
      </div>
    </Card>
  );
}

function SatisfactionRing({ percent }: { percent: number }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(Math.max(percent, 0), 100) / 100);

  return (
    <div className="relative flex size-28 shrink-0 items-center justify-center">
      <svg viewBox="0 0 64 64" className="size-28 -rotate-90">
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          strokeWidth="8"
          className="stroke-muted"
        />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="stroke-teal transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="font-mono text-xl font-semibold tabular-nums">{percent}%</p>
        <p className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Kepuasan
        </p>
      </div>
    </div>
  );
}

export function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminStats(controller.signal)
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "Gagal memuat data dashboard.";
        if (message === "Invalid or expired token." || message === "Missing bearer token.") {
          clearStoredSession();
          window.location.assign("/login-admin");
          return;
        }
        setError(message);
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-5">
          <Skeleton className="h-64 lg:col-span-3" />
          <Skeleton className="h-64 lg:col-span-2" />
        </div>
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <Card className="mx-auto mt-16 max-w-md">
        <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-red-soft text-red">
            <AlertTriangle className="size-5" />
          </span>
          <div className="space-y-1">
            <p className="font-medium">{error ?? "Data tidak tersedia."}</p>
            <p className="text-sm text-muted-foreground">
              Tidak dapat memuat statistik dashboard.
            </p>
          </div>
          <Button variant="outline" onClick={() => window.location.reload()}>
            <RefreshCw /> Muat ulang
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { documents } = stats;
  const docPercent =
    documents.total > 0 ? Math.round((documents.published / documents.total) * 100) : 0;
  const satisfaction =
    stats.feedback.total > 0
      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
      : 0;

  const pipeline = [
    {
      name: "Selesai",
      count: Math.max(documents.total - documents.needs_review - documents.failed, 0),
      barClass: "bg-teal",
      dotClass: "bg-teal",
    },
    {
      name: "Perlu review",
      count: documents.needs_review,
      barClass: "bg-amber",
      dotClass: "bg-amber",
    },
    {
      name: "Gagal",
      count: documents.failed,
      barClass: "bg-red",
      dotClass: "bg-red",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-medium tracking-[0.18em] text-teal uppercase">
            Ringkasan knowledge base
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Status dokumen, percakapan, dan feedback pengguna
          </p>
        </div>
        <Button asChild className="bg-teal text-white hover:bg-teal-strong">
          <Link href="/admin/upload">
            <Upload /> Upload dokumen
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={FileText}
          label="Total dokumen"
          value={documents.total}
          note={`${docPercent}% telah diterbitkan`}
          dotClass="bg-teal"
        />
        <StatCard
          icon={FileCheck2}
          label="Dokumen aktif"
          value={documents.published}
          note={`${documents.needs_review} menunggu review`}
          dotClass="bg-amber"
        />
        <StatCard
          icon={Users}
          label="Pengguna terdaftar"
          value={stats.users}
          note={`${stats.conversations} percakapan aktif`}
          dotClass="bg-teal"
        />
        <StatCard
          icon={MessageSquare}
          label="Total pesan"
          value={stats.messages}
          note={`${stats.feedback.total} feedback masuk`}
          dotClass="bg-teal"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Proses dokumen</CardTitle>
            <CardDescription>Status ingestion knowledge base</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-baseline gap-2">
              <p className="font-mono text-4xl font-semibold tracking-tight tabular-nums">
                {documents.total}
              </p>
              <p className="text-sm text-muted-foreground">dokumen keseluruhan</p>
            </div>

            <div className="flex h-2 overflow-hidden rounded-full bg-muted">
              {pipeline.map((item) => (
                <div
                  key={item.name}
                  className={item.barClass}
                  style={{
                    width: `${documents.total > 0 ? (item.count / documents.total) * 100 : 0}%`,
                  }}
                />
              ))}
            </div>

            <ul className="space-y-3">
              {pipeline.map((item) => (
                <li key={item.name} className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-2.5 text-sm">
                    <span className={cn("size-2 rounded-full", item.dotClass)} />
                    {item.name}
                  </span>
                  <span className="flex items-center gap-3 font-mono text-sm tabular-nums">
                    <span className="font-semibold">{item.count}</span>
                    <span className="w-10 text-right text-xs text-muted-foreground">
                      {documents.total > 0 ? Math.round((item.count / documents.total) * 100) : 0}%
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Feedback pengguna</CardTitle>
            <CardDescription>Penilaian atas jawaban asisten</CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-6">
            <SatisfactionRing percent={satisfaction} />
            <ul className="flex-1 space-y-4">
              <li className="flex items-center gap-3">
                <span className="flex size-8 items-center justify-center rounded-md bg-teal-soft text-teal">
                  <ThumbsUp className="size-4" />
                </span>
                <div className="flex-1">
                  <p className="text-sm font-medium">Membantu</p>
                  <p className="text-xs text-muted-foreground">jawaban dinilai berguna</p>
                </div>
                <p className="font-mono text-base font-semibold tabular-nums">
                  {stats.feedback.helpful}
                </p>
              </li>
              <li className="flex items-center gap-3">
                <span className="flex size-8 items-center justify-center rounded-md bg-red-soft text-red">
                  <ThumbsDown className="size-4" />
                </span>
                <div className="flex-1">
                  <p className="text-sm font-medium">Tidak membantu</p>
                  <p className="text-xs text-muted-foreground">jawaban dinilai kurang</p>
                </div>
                <p className="font-mono text-base font-semibold tabular-nums">
                  {stats.feedback.not_helpful}
                </p>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Ingestion terbaru</CardTitle>
          <CardDescription>Job pemrosesan dokumen terakhir</CardDescription>
          <CardAction>
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/ingestion">
                Lihat semua <ArrowUpRight />
              </Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="p-0">
          {stats.ingestion_jobs.recent.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <Database className="size-5" />
              </span>
              <p className="text-sm font-medium">Belum ada job ingestion</p>
              <p className="text-sm text-muted-foreground">
                Upload dokumen untuk memulai proses ingestion.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dokumen</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Waktu</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.ingestion_jobs.recent.map((job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-mono text-xs font-medium">
                      {job.document_id}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={
                          ingestionStatusBadge[job.status] ?? "bg-muted text-muted-foreground"
                        }
                      >
                        {job.status === "completed" && <CheckCircle2 />}
                        {ingestionStatusLabel[job.status] ?? job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground tabular-nums">
                      {formatDate(job.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Aksi cepat</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Button asChild variant="outline" className="h-auto flex-col gap-1.5 py-4">
              <Link href="/admin/upload">
                <Upload className="size-5 text-teal" />
                <span className="text-xs font-medium">Upload PDF</span>
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto flex-col gap-1.5 py-4">
              <Link href="/documents">
                <FileText className="size-5 text-teal" />
                <span className="text-xs font-medium">Kelola dokumen</span>
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto flex-col gap-1.5 py-4">
              <Link href="/admin/ingestion">
                <Database className="size-5 text-teal" />
                <span className="text-xs font-medium">Ingestion</span>
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto flex-col gap-1.5 py-4">
              <Link href="/admin/feedback">
                <ThumbsUp className="size-5 text-teal" />
                <span className="text-xs font-medium">Feedback</span>
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto flex-col gap-1.5 py-4">
              <Link href="/admin/retrieval">
                <FlaskConical className="size-5 text-teal" />
                <span className="text-xs font-medium">Retrieval lab</span>
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
