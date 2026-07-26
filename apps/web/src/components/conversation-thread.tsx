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
import type { AnswerPayload } from "@/lib/types";

type ConversationThreadProps = {
  messages: ChatMessage[];
  feedback: Record<string, "helpful" | "not_helpful">;
  onShowSources: (answer: AnswerPayload) => void;
  onFeedback: (message: ChatMessage, rating: "helpful" | "not_helpful") => void;
  onEditMessage: (message: ChatMessage) => void;
};

function formatMessageTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function answerBlocks(content: string) {
  const explicitBlocks = content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (explicitBlocks.length !== 1 || content.length <= 260) return explicitBlocks;

  const sentences = content.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((item) => item.trim()) ?? [
    content,
  ];
  const blocks: string[] = [];
  for (let index = 0; index < sentences.length; index += 2) {
    blocks.push(sentences.slice(index, index + 2).join(" "));
  }
  return blocks;
}

function AnswerContent({ content, streaming }: { content: string; streaming: boolean }) {
  const blocks = answerBlocks(content);
  return (
    <div
      className={streaming ? "editorial-answer-content is-streaming" : "editorial-answer-content"}
    >
      {blocks.map((block, index) => {
        const listMatch = block.match(/^(?:[-•]|\d+[.)])\s+(.+)$/);
        return listMatch ? (
          <div className="editorial-answer-point" key={`${index}-${block}`}>
            <span aria-hidden="true">{index + 1}</span>
            <p>{listMatch[1]}</p>
          </div>
        ) : (
          <p key={`${index}-${block}`}>{block}</p>
        );
      })}
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
                    onClick={() => onFeedback(message, "not_helpful")}
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
          </article>
        )
      )}
    </div>
  );
}
