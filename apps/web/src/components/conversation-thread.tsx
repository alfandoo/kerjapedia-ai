"use client";

import { AlertIcon, FileIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
import type { ChatMessage } from "./chat-types";
import type { AnswerPayload } from "@/lib/types";

type ConversationThreadProps = {
  messages: ChatMessage[];
  feedback: Record<string, "helpful" | "not_helpful">;
  onShowSources: (answer: AnswerPayload) => void;
  onFeedback: (message: ChatMessage, rating: "helpful" | "not_helpful") => void;
};

function formatMessageTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ConversationThread({
  messages,
  feedback,
  onShowSources,
  onFeedback,
}: ConversationThreadProps) {
  return (
    <div className="editorial-thread" aria-live="polite" aria-label="Percakapan">
      {messages.map((message) =>
        message.role === "user" ? (
          <article className="editorial-user-message" key={message.id}>
            <time>{formatMessageTime(message.createdAt)}</time>
            <p>{message.content}</p>
          </article>
        ) : (
          <article className="editorial-answer" key={message.id}>
            <header>
              <span className="editorial-answer-avatar">KP</span>
              <strong>
                {message.streaming ? "KerjaPedia sedang berpikir" : "Jawaban KerjaPedia"}
              </strong>
              <time>{formatMessageTime(message.createdAt)}</time>
            </header>
            {message.status && !message.content ? (
              <div className="editorial-thinking" role="status" aria-live="polite">
                <span className="editorial-thinking-dot" aria-hidden="true" />
                <span>{message.status}</span>
              </div>
            ) : (
              <p
                className={
                  message.streaming ? "editorial-answer-text is-streaming" : "editorial-answer-text"
                }
              >
                {message.content}
                {message.streaming ? (
                  <span className="streaming-cursor" aria-hidden="true" />
                ) : null}
              </p>
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
                <span>Dasar dokumen belum cukup untuk menjawab pertanyaan ini dengan aman.</span>
              </div>
            ) : null}
            {message.answer?.clarification_question ? (
              <div className="editorial-notice">
                <AlertIcon className="icon" />
                <span>{message.answer.clarification_question}</span>
              </div>
            ) : null}
            {!message.streaming ? (
              <footer>
                <span>Apakah jawaban ini membantu?</span>
                <div>
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
                </div>
              </footer>
            ) : null}
          </article>
        )
      )}
    </div>
  );
}
