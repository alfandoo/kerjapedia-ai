"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  MessageSquareQuote,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, PageHeader, StatusBadge } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import { fetchAdminFeedback } from "@/lib/api";
import { fallbackFeedback } from "@/lib/sample-data";
import type { FeedbackItem } from "@/lib/types";

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDateTime(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function relativeTime(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  const diff = Date.now() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.floor(hours / 24);
  return `${days} hari lalu`;
}

const issueLabels: Record<string, string> = {
  citation_incorrect: "Sumber tidak sesuai",
  answer_incomplete: "Jawaban kurang lengkap",
  irrelevant: "Tidak relevan",
  outdated: "Informasi usang",
};

const filterOptions = [
  { value: "all", label: "Semua" },
  { value: "helpful", label: "Membantu" },
  { value: "not_helpful", label: "Perlu perbaikan" },
] as const;

export function AdminFeedback() {
  const [items, setItems] = useState(fallbackFeedback);
  const [search, setSearch] = useState("");
  const [rating, setRating] = useState("all");
  const [loadStatus, setLoadStatus] = useState("Memuat feedback pengguna...");
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminFeedback(controller.signal)
      .then((feedback) => {
        if (feedback.length) setItems(feedback);
        setLoadStatus("Feedback tersinkron dengan API.");
      })
      .catch(() => setLoadStatus("Menampilkan data contoh — API belum tersedia."));
    return () => controller.abort();
  }, []);

  const stats = useMemo(() => {
    const total = items.length;
    const helpful = items.filter((i) => i.rating === "helpful").length;
    const notHelpful = total - helpful;
    const withComment = items.filter((i) => i.comment).length;
    return { total, helpful, notHelpful, withComment };
  }, [items]);

  const filtered = useMemo(
    () =>
      items.filter(
        (item) =>
          (rating === "all" || item.rating === rating) &&
          `${item.question} ${item.comment ?? ""}`.toLowerCase().includes(deferredSearch)
      ),
    [deferredSearch, items, rating]
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Umpan balik pengguna"
        title="Feedback"
        description={loadStatus}
      />

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="py-0">
          <CardContent className="flex items-center gap-3 py-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-soft">
              <BarChart3 className="size-5 text-tinta" />
            </span>
            <div>
              <p className="text-xs text-muted-text">Total feedback</p>
              <p className="text-2xl font-semibold tabular-nums text-tinta">{stats.total}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="py-0">
          <CardContent className="flex items-center gap-3 py-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-soft">
              <ThumbsUp className="size-5 text-forest" />
            </span>
            <div>
              <p className="text-xs text-muted-text">Membantu</p>
              <p className="text-2xl font-semibold tabular-nums text-forest">
                {stats.helpful}
                {stats.total > 0 && (
                  <span className="ml-1 text-sm font-normal text-muted-text">
                    ({Math.round((stats.helpful / stats.total) * 100)}%)
                  </span>
                )}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="py-0">
          <CardContent className="flex items-center gap-3 py-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-soft">
              <ThumbsDown className="size-5 text-red" />
            </span>
            <div>
              <p className="text-xs text-muted-text">Perlu perbaikan</p>
              <p className="text-2xl font-semibold tabular-nums text-red">
                {stats.notHelpful}
                {stats.total > 0 && (
                  <span className="ml-1 text-sm font-normal text-muted-text">
                    ({Math.round((stats.notHelpful / stats.total) * 100)}%)
                  </span>
                )}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search + filter */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-56">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-text" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cari pertanyaan atau komentar..."
            className="pl-8"
          />
        </div>
        <div className="flex gap-1.5">
          {filterOptions.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setRating(opt.value)}
              className={cn(
                "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
                rating === opt.value
                  ? "bg-javanese text-white"
                  : "bg-surface-soft text-muted-text hover:bg-teal-soft hover:text-tinta"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Feedback list */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={MessageSquareQuote}
          title="Tidak ada feedback ditemukan"
          hint="Ubah kata kunci atau filter untuk melihat hasil lain."
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => {
            const helpful = item.rating === "helpful";
            return (
              <Card key={item.feedback_id} className="py-0">
                <CardContent className="py-4">
                  <div className="flex gap-3">
                    {/* Rating icon */}
                    <span
                      className={cn(
                        "flex size-9 shrink-0 items-center justify-center rounded-xl",
                        helpful ? "bg-teal-soft text-forest" : "bg-red-soft text-red"
                      )}
                    >
                      {helpful ? (
                        <ThumbsUp className="size-4" />
                      ) : (
                        <ThumbsDown className="size-4" />
                      )}
                    </span>

                    <div className="min-w-0 flex-1 space-y-2">
                      {/* Question */}
                      <p className="text-sm font-semibold text-tinta">{item.question}</p>

                      {/* Comment */}
                      <p className="text-sm text-muted-text">
                        {item.comment ?? "Tanpa komentar tambahan."}
                      </p>

                      {/* Meta row */}
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-text">
                        <StatusBadge tone={helpful ? "success" : "danger"}>
                          {helpful ? "Membantu" : "Perlu perbaikan"}
                        </StatusBadge>
                        {item.issue_category && (
                          <StatusBadge tone="warning">
                            {issueLabels[item.issue_category] ??
                              item.issue_category.replaceAll("_", " ")}
                          </StatusBadge>
                        )}
                        <span className="text-muted-text/50">·</span>
                        <span className="font-mono">{item.user_id}</span>
                        <span className="text-muted-text/50">·</span>
                        <span title={formatDateTime(item.created_at)}>
                          {relativeTime(item.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
