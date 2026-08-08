"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { MessageSquareQuote, Search, ThumbsDown, ThumbsUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { fetchAdminFeedback } from "@/lib/api";
import { fallbackFeedback } from "@/lib/sample-data";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function AdminFeedback() {
  const [items, setItems] = useState(fallbackFeedback);
  const [search, setSearch] = useState("");
  const [rating, setRating] = useState("all");
  const [message, setMessage] = useState("Memuat feedback pengguna...");
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminFeedback(controller.signal)
      .then((feedback) => {
        if (feedback.length) setItems(feedback);
        setMessage("Feedback tersinkron dengan API.");
      })
      .catch(() => setMessage("Menampilkan feedback contoh karena API belum tersedia."));
    return () => controller.abort();
  }, []);

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
      <div className="space-y-1">
        <p className="text-xs font-medium tracking-[0.18em] text-teal uppercase">
          Umpan balik pengguna
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">Feedback</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-56">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cari pertanyaan atau komentar..."
            className="pl-8"
          />
        </div>
        <Select value={rating} onValueChange={setRating}>
          <SelectTrigger aria-label="Filter rating feedback">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua rating</SelectItem>
            <SelectItem value="helpful">Membantu</SelectItem>
            <SelectItem value="not_helpful">Tidak membantu</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Daftar feedback</CardTitle>
          <CardDescription>
            {filtered.length} dari {items.length} feedback
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <ul className="divide-y">
            {filtered.map((item) => {
              const helpful = item.rating === "helpful";
              return (
                <li key={item.feedback_id} className="flex gap-4 px-4 py-4">
                  <span
                    className={cn(
                      "flex size-9 shrink-0 items-center justify-center rounded-md",
                      helpful ? "bg-teal-soft text-teal" : "bg-red-soft text-red"
                    )}
                  >
                    {helpful ? <ThumbsUp className="size-4" /> : <ThumbsDown className="size-4" />}
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-sm font-medium">{item.question}</p>
                    <p className="text-sm text-muted-foreground">
                      {item.comment ?? "Tanpa komentar tambahan."}
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      <span className="font-mono">{item.user_id}</span>
                      {item.conversation_id ? (
                        <>
                          {" · "}
                          <span className="font-mono">{item.conversation_id}</span>
                        </>
                      ) : null}
                      {" · "}
                      {formatDateTime(item.created_at)}
                    </p>
                  </div>
                  <Badge
                    variant="secondary"
                    className={cn(
                      "hidden shrink-0 sm:inline-flex",
                      item.issue_category && "bg-amber-soft text-amber"
                    )}
                  >
                    {item.issue_category?.replaceAll("_", " ") ??
                      (helpful ? "Membantu" : "Perlu review")}
                  </Badge>
                </li>
              );
            })}
            {filtered.length === 0 ? (
              <li className="flex flex-col items-center gap-2 px-4 py-12 text-center">
                <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <MessageSquareQuote className="size-5" />
                </span>
                <p className="text-sm font-medium">Tidak ada feedback yang cocok</p>
                <p className="text-sm text-muted-foreground">
                  Ubah kata kunci atau filter untuk melihat hasil lain.
                </p>
              </li>
            ) : null}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
