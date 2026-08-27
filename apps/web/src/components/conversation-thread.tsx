"use client";

import { useEffect, useState } from "react";

import {
  AlertTriangle,
  Copy,
  FileText,
  Pencil,
  Share2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import type { ChatMessage } from "./chat-types";
import type { FeedbackIssue, FeedbackRating } from "@/lib/api";
import type { AnswerPayload } from "@/lib/types";

type FeedbackDetail = {
  issue: FeedbackIssue;
  comment: string;
};

type ConversationThreadProps = {
  messages: ChatMessage[];
  feedback: Record<string, FeedbackRating>;
  onShowSources: (answer: AnswerPayload) => void;
  onFeedback: (message: ChatMessage, rating: FeedbackRating, detail?: FeedbackDetail) => void;
  onEditMessage: (message: ChatMessage) => void;
};

const FEEDBACK_ISSUE_LABELS: { value: FeedbackIssue; label: string }[] = [
  { value: "citation_incorrect", label: "Citation tidak tepat" },
  { value: "answer_incomplete", label: "Jawaban tidak lengkap" },
  { value: "outdated_regulation", label: "Regulasi sudah tidak berlaku" },
  { value: "other", label: "Lainnya" },
];

const WARNING_LABELS: Record<string, string> = {
  retrieved_source_status_needs_verification:
    "Status hukum sumber belum diverifikasi — verifikasi sebelum digunakan.",
  retrieved_source_contains_historical_or_revoked_document:
    "Sebagian sumber berstatus historis atau dicabut.",
  retrieved_source_superseded_by_newer_document:
    "Sebagian sumber telah diubah atau diganti oleh peraturan yang lebih baru.",
  retrieved_source_revoked_or_superseded_document:
    "Sumber dicabut atau digantikan oleh peraturan yang lebih baru.",
};

function formatMessageTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

type AnswerBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] };

function inlineRendered(text: string) {
  return text.split(/(\*\*[^*\n]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={index}>{part}</span>
    )
  );
}

function answerBlocks(content: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let pendingParagraph: string[] = [];
  let listItems: string[] = [];
  let ordered = false;
  let inList = false;

  const flushParagraph = () => {
    if (pendingParagraph.length) {
      const text = pendingParagraph.join(" ").trim();
      if (text) {
        blocks.push({ kind: "paragraph", text });
      }
      pendingParagraph = [];
    }
  };
  const flushList = () => {
    if (inList) {
      blocks.push({ kind: "list", ordered, items: listItems });
      listItems = [];
      inList = false;
    }
  };

  for (const raw of content.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }
    const bulletMatch = line.match(/^(?:[-•∙])\s+(.+)$/);
    const numberMatch = line.match(/^\d+[.)]\s+(.+)$/);
    if (bulletMatch || numberMatch) {
      flushParagraph();
      const isOrdered = Boolean(numberMatch);
      if (inList && ordered !== isOrdered) flushList();
      ordered = isOrdered;
      inList = true;
      listItems.push((bulletMatch ?? numberMatch)![1]);
    } else {
      flushList();
      pendingParagraph.push(line);
    }
  }
  flushList();
  flushParagraph();
  return blocks;
}

function AnswerContent({ content, streaming }: { content: string; streaming: boolean }) {
  const blocks = answerBlocks(content);
  return (
    <div className="mt-1 mb-2 text-[13.5px] leading-[1.75] text-[#2a342e] [&_strong]:font-bold [&_strong]:text-javanese">
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          block.ordered ? (
            <ol
              className="mb-3 mt-2 grid max-w-[76ch] list-none gap-1.5 p-0 [counter-reset:answer-point] last:mb-0"
              key={`list-${index}`}
            >
              {block.items.map((item) => (
                <li
                  key={item}
                  className="grid grid-cols-[22px_minmax(0,1fr)] gap-2 pl-0 [counter-increment:answer-point] before:mt-0.5 before:grid before:size-[20px] before:place-items-center before:rounded-full before:bg-javanese/10 before:text-[10px] before:font-bold before:text-javanese before:content-[counter(answer-point)]"
                >
                  {inlineRendered(item)}
                </li>
              ))}
            </ol>
          ) : (
            <ul
              className="mb-3 mt-2 grid max-w-[76ch] list-none gap-1.5 p-0 last:mb-0"
              key={`list-${index}`}
            >
              {block.items.map((item) => (
                <li
                  key={item}
                  className="grid grid-cols-[22px_minmax(0,1fr)] gap-2 pl-0 before:mt-[9px] before:ml-[7px] before:size-[6px] before:rounded-full before:bg-javanese/60"
                >
                  {inlineRendered(item)}
                </li>
              ))}
            </ul>
          )
        ) : (
          <p className="mb-2.5 max-w-[74ch] whitespace-pre-wrap last:mb-0" key={`p-${index}`}>
            {inlineRendered(block.text)}
          </p>
        )
      )}
      {streaming ? (
        <span
          className="ml-[3px] inline-block h-[1.05em] w-0.5 bg-javanese align-[-0.14em] [animation:streaming-cursor-blink_0.8s_steps(1)_infinite]"
          aria-hidden="true"
        />
      ) : null}
    </div>
  );
}

export function ConversationThread({
  messages,
  feedback,
  onShowSources,
  onFeedback,
  onEditMessage,
}: ConversationThreadProps) {
  const [actionStatus, setActionStatus] = useState<{ messageId: string; text: string } | null>(
    null
  );
  const [feedbackPanel, setFeedbackPanel] = useState<{ messageId: string } | null>(null);
  const [issueSelection, setIssueSelection] = useState<FeedbackIssue | null>(null);
  const [issueComment, setIssueComment] = useState("");

  useEffect(() => {
    if (!actionStatus) return;
    const timer = window.setTimeout(() => setActionStatus(null), 1800);
    return () => window.clearTimeout(timer);
  }, [actionStatus]);

  async function copyText(messageId: string, content: string, successText = "Tersalin") {
    try {
      await navigator.clipboard.writeText(content);
      setActionStatus({ messageId, text: successText });
    } catch {
      setActionStatus({ messageId, text: "Tidak dapat menyalin" });
    }
  }

  async function shareAnswer(message: ChatMessage) {
    const shareData = {
      title: "Jawaban KerjaPedia",
      text: message.content,
    };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
        setActionStatus({ messageId: message.id, text: "Berhasil dibagikan" });
        return;
      } catch (error) {
        if ((error as DOMException).name === "AbortError") return;
      }
    }
    await copyText(message.id, message.content, "Jawaban disalin untuk dibagikan");
  }

  return (
    <div
      className="mx-auto w-full max-w-[760px]"
      aria-live="polite"
      aria-label="Percakapan"
    >
      {messages.map((message) =>
        message.role === "user" ? (
          <article
            className="mb-5 flex flex-col items-end pl-[68px] max-[760px]:pl-0"
            key={message.id}
          >
            <p className="max-w-[min(82%,560px)] rounded-[18px_18px_4px_18px] bg-[#eef4f0] px-4 py-[11px] text-[13px] leading-[1.55] text-[#29332d]">
              {message.content}
            </p>
            <div className="mt-1 flex min-h-[28px] items-center justify-end gap-1">
              <time
                className="font-mono text-[10px] leading-[1.4] tabular-nums text-[#a0a8a3]"
                title={formatMessageTime(message.createdAt)}
              >
                {formatMessageTime(message.createdAt)}
              </time>
              <div className="flex min-h-7 items-center gap-0.5">
                <button
                  type="button"
                  className="grid size-7 place-items-center rounded-lg border border-transparent text-[#8a928d] transition hover:bg-[#eef2ef] hover:text-[#26312b]"
                  aria-label="Edit pesan"
                  title="Edit pesan"
                  onClick={() => onEditMessage(message)}
                >
                  <Pencil className="size-[16px]" />
                </button>
                <button
                  type="button"
                  className="grid size-7 place-items-center rounded-lg border border-transparent text-[#8a928d] transition hover:bg-[#eef2ef] hover:text-[#26312b]"
                  aria-label="Salin pesan"
                  title="Salin pesan"
                  onClick={() => void copyText(message.id, message.content)}
                >
                      <Copy className="size-[16px]" />
                </button>
                {actionStatus?.messageId === message.id ? (
                  <span className="mx-1 whitespace-nowrap text-[11px] text-muted-text" role="status">
                    {actionStatus.text}
                  </span>
                ) : null}
              </div>
            </div>
          </article>
        ) : (
          <article className="mb-6" key={message.id}>
            <div className="rounded-xl border-l-[3px] border-javanese/20 pl-4 transition-colors group-hover:border-javanese/40 max-[760px]:pl-3">
              <header className="mb-2 flex items-center gap-2.5">
                <span className="grid size-[28px] place-items-center rounded-lg bg-javanese/10 text-[9px] font-bold text-javanese">
                  KP
                </span>
                <strong className="text-[12px] font-semibold text-[#4a564e]">
                  {message.streaming ? "Berpikir…" : "Jawaban KerjaPedia"}
                </strong>
                <time
                  className="font-mono text-[10px] leading-[1.4] tabular-nums text-[#a0a8a3]"
                  title={formatMessageTime(message.createdAt)}
                >
                  {formatMessageTime(message.createdAt)}
                </time>
              </header>
              {message.status && !message.content ? (
                <div className="inline-flex min-h-[38px] items-center gap-2 text-[13px] text-[#65726b]" role="status" aria-live="polite">
                  <span
                    className="size-2 rounded-full bg-javanese [animation:editorial-thinking-pulse_1.4s_ease-in-out_infinite]"
                    aria-hidden="true"
                  />
                  <span>{message.status}</span>
                </div>
              ) : (
                <AnswerContent content={message.content} streaming={Boolean(message.streaming)} />
              )}
              {message.answer?.citations.length ? (
                <button
                  className="mt-1 inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border border-[#e2e8e2] bg-[#fafbf9] px-3 text-[11px] font-semibold text-javanese transition hover:border-javanese/40 hover:bg-[#f0f5f1]"
                  type="button"
                  onClick={() => onShowSources(message.answer as AnswerPayload)}
                >
                  <FileText className="size-[16px]" />
                  {message.answer.citations.length} sumber resmi
                  <span aria-hidden="true" className="text-[10px]">→</span>
                </button>
              ) : null}
              {message.answer?.refusal_reason ? (
                <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-[#f0e6d2] bg-[#fffcf5] p-3 text-xs leading-[1.55] text-[#88540d]">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>
                    {message.answer.refusal_reason === "out_of_scope_query"
                      ? "KerjaPedia AI hanya menjawab topik ketenagakerjaan Indonesia."
                      : message.answer.refusal_reason === "prompt_injection_detected"
                        ? "Permintaan diblokir oleh sistem keamanan."
                        : "Dasar dokumen belum cukup untuk menjawab pertanyaan ini dengan aman."}
                  </span>
                </div>
              ) : null}
              {message.answer?.clarification_question ? (
                <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-[#f0e6d2] bg-[#fffcf5] p-3 text-xs leading-[1.55] text-[#88540d]">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{message.answer.clarification_question}</span>
                </div>
              ) : null}
              {message.answer?.warnings?.length ? (
                <div className="mt-3 grid gap-1.5">
                  {message.answer.warnings.map((code) => {
                    const label = WARNING_LABELS[code];
                    if (!label) return null;
                    return (
                      <div
                        className="flex items-start gap-2.5 rounded-lg border border-[#f0e6d2] bg-[#fffcf5] p-3 text-xs leading-[1.55] text-[#88540d]"
                        key={code}
                      >
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                        <span>{label}</span>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {!message.streaming ? (
                <footer className="mt-2 flex min-h-[30px] items-center text-[11px] text-muted-text">
                  <div className="flex gap-0.5">
                    <button
                      type="button"
                      className="grid size-7 place-items-center rounded-lg border border-transparent text-[#8a928d] transition hover:bg-[#eef2ef] hover:text-[#26312b]"
                      aria-label="Salin jawaban"
                      title="Salin jawaban"
                      onClick={() => void copyText(message.id, message.content)}
                    >
                  <Copy className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className={`grid size-7 place-items-center rounded-lg border transition ${
                        feedback[message.id] === "helpful"
                          ? "border-javanese/30 bg-[#f0f5f1] text-javanese"
                          : "border-transparent text-[#8a928d] hover:bg-[#eef2ef] hover:text-[#26312b]"
                      }`}
                      aria-label="Tandai jawaban membantu"
                      aria-pressed={feedback[message.id] === "helpful"}
                      onClick={() => onFeedback(message, "helpful")}
                    >
                      <ThumbsUp className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className={`grid size-7 place-items-center rounded-lg border transition ${
                        feedback[message.id] === "not_helpful"
                          ? "border-javanese/30 bg-[#f0f5f1] text-javanese"
                          : "border-transparent text-[#8a928d] hover:bg-[#eef2ef] hover:text-[#26312b]"
                      }`}
                      aria-label="Tandai jawaban tidak membantu"
                      aria-pressed={feedback[message.id] === "not_helpful"}
                      onClick={() => {
                        if (feedbackPanel?.messageId === message.id) {
                          setFeedbackPanel(null);
                        } else {
                          setFeedbackPanel({ messageId: message.id });
                          setIssueSelection(null);
                          setIssueComment("");
                        }
                      }}
                    >
                      <ThumbsDown className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className="grid size-7 place-items-center rounded-lg border border-transparent text-[#8a928d] transition hover:bg-[#eef2ef] hover:text-[#26312b]"
                      aria-label="Bagikan jawaban"
                      title="Bagikan jawaban"
                      onClick={() => void shareAnswer(message)}
                    >
                      <Share2 className="size-[16px]" />
                    </button>
                  </div>
                  {actionStatus?.messageId === message.id ? (
                    <span className="mx-1 whitespace-nowrap text-[11px] text-muted-text" role="status">
                      {actionStatus.text}
                    </span>
                  ) : null}
                </footer>
              ) : null}
            </div>
            {feedbackPanel?.messageId === message.id ? (
              <div
                className="mt-3 ml-4 grid max-w-[420px] gap-2.5 rounded-xl border border-[#e2e8e2] bg-[#fafbf9] p-3.5 max-[760px]:ml-3"
                role="group"
                aria-label="Detail feedback"
              >
                <p className="text-[13px] font-bold text-[#26312b]">Apa yang perlu diperbaiki?</p>
                <div className="flex flex-wrap gap-1.5">
                  {FEEDBACK_ISSUE_LABELS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`rounded-full border px-2.5 py-1.5 text-xs transition hover:border-javanese hover:text-javanese ${
                        issueSelection === option.value
                          ? "border-javanese bg-[#edf4f0] font-semibold text-javanese"
                          : "border-[#dbe4db] bg-white text-[#4a564e]"
                      }`}
                      aria-pressed={issueSelection === option.value}
                      onClick={() => setIssueSelection(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <textarea
                  className="w-full resize-y rounded-lg border border-[#dbe4db] bg-white p-2.5 text-[13px] leading-normal text-tinta outline-none transition focus:border-javanese focus:outline-2 focus:outline-offset-1 focus:outline-javanese/40"
                  rows={3}
                  maxLength={1000}
                  placeholder="Tambahkan detail (opsional)..."
                  value={issueComment}
                  onChange={(event) => setIssueComment(event.target.value)}
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    className="rounded-lg px-3 py-[7px] text-[13px] text-[#68736c] transition hover:bg-[#eef2ef]"
                    onClick={() => setFeedbackPanel(null)}
                  >
                    Batal
                  </button>
                  <button
                    type="button"
                    className="rounded-lg bg-javanese px-3.5 py-[7px] text-[13px] font-semibold text-white transition hover:bg-forest disabled:cursor-not-allowed disabled:bg-[#c9d3cb]"
                    disabled={!issueSelection}
                    onClick={() => {
                      const detail: FeedbackDetail | undefined = issueSelection
                        ? { issue: issueSelection, comment: issueComment.trim() }
                        : undefined;
                      onFeedback(message, "not_helpful", detail);
                      setFeedbackPanel(null);
                    }}
                  >
                    Kirim feedback
                  </button>
                </div>
              </div>
            ) : null}
          </article>
        )
      )}
    </div>
  );
}
