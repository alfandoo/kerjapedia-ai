"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { SearchIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
import { fetchAdminFeedback } from "@/lib/api";
import { fallbackFeedback } from "@/lib/sample-data";

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
    <section className="admin-standard-page">
      <div className="admin-page-heading">
        <div>
          <h1>User Feedback</h1>
          <p>{message}</p>
        </div>
      </div>
      <div className="admin-table-toolbar feedback-toolbar">
        <label className="admin-search-field">
          <SearchIcon className="icon" />
          <span className="sr-only">Cari feedback</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cari pertanyaan atau komentar..."
          />
        </label>
        <select
          value={rating}
          onChange={(event) => setRating(event.target.value)}
          aria-label="Filter rating feedback"
        >
          <option value="all">Semua rating</option>
          <option value="helpful">Membantu</option>
          <option value="not_helpful">Tidak membantu</option>
        </select>
      </div>
      <div className="feedback-list">
        {filtered.map((item) => (
          <article className="feedback-row" key={item.feedback_id}>
            <span
              className={
                item.rating === "helpful" ? "feedback-rating positive" : "feedback-rating negative"
              }
            >
              {item.rating === "helpful" ? (
                <ThumbsUpIcon className="icon" />
              ) : (
                <ThumbsDownIcon className="icon" />
              )}
            </span>
            <div>
              <h2>{item.question}</h2>
              <p>{item.comment ?? "Tanpa komentar tambahan."}</p>
              <small>
                {item.user_id} · {new Date(item.created_at).toLocaleString("id-ID")}
              </small>
            </div>
            <span className="status-badge">
              {item.issue_category?.replaceAll("_", " ") ??
                (item.rating === "helpful" ? "Membantu" : "Perlu review")}
            </span>
          </article>
        ))}
        {filtered.length === 0 ? (
          <p className="admin-empty-copy">Tidak ada feedback yang cocok.</p>
        ) : null}
      </div>
    </section>
  );
}
