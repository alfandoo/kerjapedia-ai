"use client";

import { useEffect, useState } from "react";

import {
  AlertIcon,
  CopyIcon,
  EditIcon,
  FileIcon,
  ShareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "./icons";
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
      blocks.push({ kind: "paragraph", text: pendingParagraph.join(" ") });
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
    <div
      className={streaming ? "editorial-answer-content is-streaming" : "editorial-answer-content"}
    >
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          block.ordered ? (
            <ol className="editorial-answer-list editorial-answer-ordered" key={`list-${index}`}>
              {block.items.map((item) => (
                <li key={item}>{inlineRendered(item)}</li>
              ))}
            </ol>
          ) : (
            <ul className="editorial-answer-list" key={`list-${index}`}>
              {block.items.map((item) => (
                <li key={item}>{inlineRendered(item)}</li>
              ))}
            </ul>
          )
        ) : (
          <p key={`p-${index}`}>{inlineRendered(block.text)}</p>
        )
      )}
      {streaming ? <span className="streaming-cursor" aria-hidden="true" /> : null}
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
    <div className="editorial-thread" aria-live="polite" aria-label="Percakapan">
      {messages.map((message) =>
        message.role === "user" ? (
          <article className="editorial-user-message" key={message.id}>
            <p>{message.content}</p>
            <div className="user-message-meta">
              <time className="message-time" title={formatMessageTime(message.createdAt)}>
                {formatMessageTime(message.createdAt)}
              </time>
              <div className="message-action-bar user-message-actions">
                <button
                  type="button"
                  aria-label="Edit pesan"
                  title="Edit pesan"
                  onClick={() => onEditMessage(message)}
                >
                  <EditIcon className="icon" />
                </button>
                <button
                  type="button"
                  aria-label="Salin pesan"
                  title="Salin pesan"
                  onClick={() => void copyText(message.id, message.content)}
                >
                  <CopyIcon className="icon" />
                </button>
                {actionStatus?.messageId === message.id ? (
                  <span className="message-action-status" role="status">
                    {actionStatus.text}
                  </span>
                ) : null}
              </div>
            </div>
          </article>
        ) : (
          <article className="editorial-answer" key={message.id}>
            <header>
              <span className="editorial-answer-avatar">KP</span>
              <strong>
                {message.streaming ? "KerjaPedia sedang berpikir" : "Jawaban KerjaPedia"}
              </strong>
              <time className="message-time" title={formatMessageTime(message.createdAt)}>
                {formatMessageTime(message.createdAt)}
              </time>
            </header>
            {message.status && !message.content ? (
              <div className="editorial-thinking" role="status" aria-live="polite">
                <span className="editorial-thinking-dot" aria-hidden="true" />
                <span>{message.status}</span>
              </div>
            ) : (
              <AnswerContent content={message.content} streaming={Boolean(message.streaming)} />
            )}
            {message.answer?.citations.length ? (
              <button
                className="editorial-source-action"
                type="button"
                onClick={() => onShowSources(message.answer as AnswerPayload)}
              >
                <FileIcon className="icon" />
                Lihat {message.answer.citations.length} sumber resmi
                <span aria-hidden="true">→</span>
              </button>
            ) : null}
            {message.answer?.refusal_reason ? (
              <div className="editorial-notice">
                <AlertIcon className="icon" />
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
              <div className="editorial-notice">
                <AlertIcon className="icon" />
                <span>{message.answer.clarification_question}</span>
              </div>
            ) : null}
            {message.answer?.warnings?.length ? (
              <div className="editorial-warning-list">
                {message.answer.warnings.map((code) => {
                  const label = WARNING_LABELS[code];
                  if (!label) return null;
                  return (
                    <div className="editorial-notice" key={code}>
                      <AlertIcon className="icon" />
                      <span>{label}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}
            {!message.streaming ? (
              <footer className="message-action-bar assistant-message-actions">
                <div className="message-action-buttons">
                  <button
                    type="button"
                    aria-label="Salin jawaban"
                    title="Salin jawaban"
                    onClick={() => void copyText(message.id, message.content)}
                  >
                    <CopyIcon className="icon" />
                  </button>
                  <button
                    type="button"
                    className={feedback[message.id] === "helpful" ? "active" : ""}
                    aria-label="Tandai jawaban membantu"
                    aria-pressed={feedback[message.id] === "helpful"}
                    onClick={() => onFeedback(message, "helpful")}
                  >
                    <ThumbsUpIcon className="icon" />
                  </button>
                  <button
                    type="button"
                    className={feedback[message.id] === "not_helpful" ? "active" : ""}
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
                    <ThumbsDownIcon className="icon" />
                  </button>
                  <button
                    type="button"
                    aria-label="Bagikan jawaban"
                    title="Bagikan jawaban"
                    onClick={() => void shareAnswer(message)}
                  >
                    <ShareIcon className="icon" />
                  </button>
                </div>
                {actionStatus?.messageId === message.id ? (
                  <span className="message-action-status" role="status">
                    {actionStatus.text}
                  </span>
                ) : null}
              </footer>
            ) : null}
            {feedbackPanel?.messageId === message.id ? (
              <div className="editorial-feedback-panel" role="group" aria-label="Detail feedback">
                <p className="editorial-feedback-title">Apa yang perlu diperbaiki?</p>
                <div className="editorial-feedback-options">
                  {FEEDBACK_ISSUE_LABELS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={issueSelection === option.value ? "active" : ""}
                      aria-pressed={issueSelection === option.value}
                      onClick={() => setIssueSelection(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <textarea
                  className="editorial-feedback-comment"
                  rows={3}
                  maxLength={1000}
                  placeholder="Tambahkan detail (opsional)..."
                  value={issueComment}
                  onChange={(event) => setIssueComment(event.target.value)}
                />
                <div className="editorial-feedback-actions">
                  <button
                    type="button"
                    className="editorial-feedback-cancel"
                    onClick={() => setFeedbackPanel(null)}
                  >
                    Batal
                  </button>
                  <button
                    type="button"
                    className="editorial-feedback-submit"
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
