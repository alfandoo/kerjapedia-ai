"use client";

import { useRef, useState } from "react";

import { AlertIcon, ChatIcon, SendIcon, StopIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
import { askQuestion, submitFeedback } from "@/lib/api";
import type { AnswerPayload, Citation } from "@/lib/types";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: AnswerPayload;
};

type ChatWorkspaceProps = {
  onCitationsChange: (citations: Citation[], question: string) => void;
};

const suggestions = [
  "Berapa hak cuti tahunan karyawan sesuai UU Ketenagakerjaan?",
  "Syarat dan prosedur PHK karena efisiensi perusahaan",
  "Apakah karyawan kontrak berhak atas THR?",
];

export function ChatWorkspace({ onCitationsChange }: ChatWorkspaceProps) {
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamRef = useRef<number | null>(null);

  function stopGeneration() {
    abortRef.current?.abort();
    abortRef.current = null;
    if (streamRef.current) {
      window.clearInterval(streamRef.current);
      streamRef.current = null;
    }
    setIsLoading(false);
    setIsStreaming(false);
  }

  function streamAnswer(answer: AnswerPayload) {
    const id = crypto.randomUUID();
    const fullText = answer.answer;
    let index = 0;
    setIsStreaming(true);
    setMessages((current) => [...current, { id, role: "assistant", content: "", answer }]);
    streamRef.current = window.setInterval(() => {
      index += 18;
      setMessages((current) =>
        current.map((message) =>
          message.id === id ? { ...message, content: fullText.slice(0, index) } : message
        )
      );
      if (index >= fullText.length && streamRef.current) {
        window.clearInterval(streamRef.current);
        streamRef.current = null;
        setIsStreaming(false);
      }
    }, 18);
  }

  async function handleSubmit(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (!trimmed || isLoading || isStreaming) {
      return;
    }
    setError(null);
    setQuestion("");
    setIsLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: trimmed },
    ]);

    try {
      const response = await askQuestion(trimmed, conversationId, controller.signal);
      setConversationId(response.conversation_id);
      onCitationsChange(response.answer.citations, trimmed);
      streamAnswer(response.answer);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
      }
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  }

  async function handleFeedback(message: ChatMessage, rating: "helpful" | "not_helpful") {
    await submitFeedback({
      question: message.answer?.query ?? "Feedback chat",
      rating,
      answer_id: message.id,
    }).catch(() => undefined);
  }

  return (
    <section className="chat-workspace">
      <div className="chat-heading">
        <span className="heading-mark">
          <ChatIcon className="icon" />
        </span>
        <div>
          <h1>Tanya regulasi ketenagakerjaan</h1>
          <p>Dapatkan jawaban berbasis sumber resmi dan kutipan pasal.</p>
        </div>
      </div>

      {messages.length === 0 ? (
        <div className="empty-state">
          <p>Contoh pertanyaan yang bisa Anda ajukan:</p>
          <div className="suggestion-list">
            {suggestions.map((item) => (
              <button key={item} type="button" onClick={() => void handleSubmit(item)}>
                <ChatIcon className="icon" />
                {item}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="message-list" aria-live="polite">
          {messages.map((message) =>
            message.role === "user" ? (
              <div className="message-row user" key={message.id}>
                <p>{message.content}</p>
              </div>
            ) : (
              <article className="answer-card" key={message.id}>
                <p className="answer-text">{message.content}</p>
                {message.answer?.citations.length ? (
                  <div className="citation-chips">
                    <span>Sumber ({message.answer.citations.length})</span>
                    {message.answer.citations.map((citation, index) => (
                      <button
                        key={citation.citation_id}
                        type="button"
                        onClick={() =>
                          onCitationsChange(
                            message.answer?.citations ?? [],
                            message.answer?.query ?? ""
                          )
                        }
                      >
                        {index + 1} {citation.short_title}
                      </button>
                    ))}
                  </div>
                ) : null}
                {message.answer?.refusal_reason ? (
                  <div className="state-strip muted">
                    <AlertIcon className="icon" />
                    {message.answer.refusal_reason}
                  </div>
                ) : null}
                <div className="answer-actions">
                  <button type="button" onClick={() => void handleFeedback(message, "helpful")}>
                    <ThumbsUpIcon className="icon" />
                  </button>
                  <button type="button" onClick={() => void handleFeedback(message, "not_helpful")}>
                    <ThumbsDownIcon className="icon" />
                  </button>
                </div>
              </article>
            )
          )}
        </div>
      )}

      {isLoading ? (
        <div className="state-strip loading">
          <span className="spinner" />
          Sedang mencari jawaban paling relevan...
        </div>
      ) : null}
      {error ? (
        <div className="state-strip error">
          <AlertIcon className="icon" />
          Gagal mengambil jawaban. {error}
        </div>
      ) : null}

      <form
        className="question-box"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSubmit();
        }}
      >
        <label htmlFor="question-input">Ketik pertanyaan Anda</label>
        <textarea
          id="question-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ketik pertanyaan Anda di sini..."
          maxLength={2000}
          rows={2}
        />
        <span>{question.length}/2000</span>
        <div className="composer-actions">
          <button
            className="send-button"
            type="submit"
            disabled={!question.trim() || isLoading || isStreaming}
          >
            <SendIcon className="icon" />
            <span>Kirim</span>
          </button>
          <button
            className="stop-button"
            type="button"
            onClick={stopGeneration}
            disabled={!isLoading && !isStreaming}
          >
            <StopIcon className="icon" />
            <span>Stop</span>
          </button>
        </div>
      </form>
    </section>
  );
}
