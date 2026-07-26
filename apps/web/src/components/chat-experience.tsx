"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "./app-shell";
import { AlertIcon, ChatIcon, SendIcon, StopIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
import { SourcePanel } from "./source-panel";
import { SourceSheet } from "./source-sheet";
import { askQuestion, fetchConversation, fetchConversations, submitFeedback } from "@/lib/api";
import type { AnswerPayload, Citation, ConversationSummary } from "@/lib/types";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: AnswerPayload;
};

const suggestions = [
  "Kapan batas waktu pembayaran THR?",
  "Apakah pekerja PKWT berhak atas uang kompensasi?",
  "Apa syarat PHK karena efisiensi perusahaan?",
];

export function ChatExperience() {
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationQuestion, setCitationQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [isSourceSheetOpen, setIsSourceSheetOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "helpful" | "not_helpful">>({});
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);

  const closeSourceSheet = useCallback(() => {
    setIsSourceSheetOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setConversations(await fetchConversations(signal));
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadInitialHistory() {
      try {
        setConversations(await fetchConversations(controller.signal));
      } catch (err) {
        if ((err as Error).name !== "AbortError") setError("Riwayat belum dapat dimuat.");
      } finally {
        setHistoryLoading(false);
      }
    }

    void loadInitialHistory();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (messages.length === 0 && !isLoading) return;
    conversationEndRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "nearest",
    });
  }, [isLoading, messages.length]);

  function stopRequest() {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
    setError("Permintaan dibatalkan. Pertanyaan Anda tidak dikirim ulang.");
  }

  function showSources(answer: AnswerPayload) {
    setCitations(answer.citations);
    setCitationQuestion(answer.query);
    if (window.matchMedia("(max-width: 1180px)").matches) {
      setIsSourceSheetOpen(true);
    }
  }

  async function handleConversationSelect(nextConversationId: string) {
    if (isLoading || nextConversationId === conversationId) return;
    setError(null);
    setHistoryLoading(true);
    try {
      const detail = await fetchConversation(nextConversationId);
      const nextMessages = detail.messages.flatMap<ChatMessage>((message, index) => {
        if (message.role !== "user" && message.role !== "assistant") return [];
        return [
          {
            id: `${detail.conversation_id}-${index}`,
            role: message.role,
            content: message.content,
            answer: message.metadata.answer,
          },
        ];
      });
      const latestAnswer = [...nextMessages]
        .reverse()
        .find((message) => message.role === "assistant" && message.answer)?.answer;
      setConversationId(detail.conversation_id);
      setMessages(nextMessages);
      setCitations(latestAnswer?.citations ?? []);
      setCitationQuestion(latestAnswer?.query ?? "");
      setIsSourceSheetOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setHistoryLoading(false);
    }
  }

  function handleNewConversation() {
    if (isLoading) stopRequest();
    setConversationId(null);
    setMessages([]);
    setCitations([]);
    setCitationQuestion("");
    setError(null);
    setIsSourceSheetOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function handleSubmit(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (!trimmed || isLoading) return;

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
      setCitations(response.answer.citations);
      setCitationQuestion(trimmed);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.answer.answer,
          answer: response.answer,
        },
      ]);
      await refreshHistory();
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  }

  async function handleFeedback(message: ChatMessage, rating: "helpful" | "not_helpful") {
    setFeedback((current) => ({ ...current, [message.id]: rating }));
    await submitFeedback({
      question: message.answer?.query ?? "Feedback chat",
      rating,
      answer_id: message.id,
    }).catch(() => setError("Feedback belum dapat disimpan."));
  }

  return (
    <AppShell
      rightPanel={<SourcePanel citations={citations} question={citationQuestion} />}
      conversations={conversations}
      activeConversationId={conversationId}
      historyLoading={historyLoading}
      onConversationSelect={(id) => void handleConversationSelect(id)}
      onNewConversation={handleNewConversation}
    >
      <section className="chat-workspace">
        <div className="chat-heading">
          <span className="heading-mark">
            <ChatIcon className="icon" />
          </span>
          <div>
            <span className="eyebrow">Asisten regulasi ketenagakerjaan</span>
            <h1>Tanyakan hak kerja Anda dengan sumber yang jelas</h1>
            <p>Jawaban dirangkum dari dokumen resmi dan selalu dapat Anda periksa kembali.</p>
          </div>
        </div>

        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="trust-banner">
              <strong>Jawaban berbasis dokumen, bukan tebakan.</strong>
              <span>KerjaPedia akan menolak jika sumber yang tersedia tidak cukup.</span>
            </div>
            <p>Mulai dengan salah satu pertanyaan berikut:</p>
            <div className="suggestion-list">
              {suggestions.map((item) => (
                <button key={item} type="button" onClick={() => void handleSubmit(item)}>
                  <ChatIcon className="icon" />
                  <span>{item}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="message-list" aria-live="polite" aria-label="Percakapan">
            {messages.map((message) =>
              message.role === "user" ? (
                <div className="message-row user" key={message.id}>
                  <p>{message.content}</p>
                </div>
              ) : (
                <article className="answer-card" key={message.id}>
                  <div className="answer-kicker">
                    <span className="answer-mark">KP</span>
                    <span>Jawaban KerjaPedia</span>
                  </div>
                  <p className="answer-text">{message.content}</p>
                  {message.answer?.citations.length ? (
                    <button
                      className="sources-trigger"
                      type="button"
                      onClick={() => showSources(message.answer as AnswerPayload)}
                    >
                      Lihat {message.answer.citations.length} sumber resmi
                      <span aria-hidden="true">→</span>
                    </button>
                  ) : null}
                  {message.answer?.refusal_reason ? (
                    <div className="state-strip muted">
                      <AlertIcon className="icon" />
                      <span>
                        Dasar dokumen belum cukup untuk menjawab pertanyaan ini dengan aman.
                      </span>
                    </div>
                  ) : null}
                  {message.answer?.clarification_question ? (
                    <div className="state-strip muted">
                      <AlertIcon className="icon" />
                      <span>{message.answer.clarification_question}</span>
                    </div>
                  ) : null}
                  <div className="answer-footer">
                    <span>Apakah jawaban ini membantu?</span>
                    <div className="answer-actions">
                      <button
                        type="button"
                        className={feedback[message.id] === "helpful" ? "active" : ""}
                        aria-label="Tandai jawaban membantu"
                        aria-pressed={feedback[message.id] === "helpful"}
                        onClick={() => void handleFeedback(message, "helpful")}
                      >
                        <ThumbsUpIcon className="icon" />
                      </button>
                      <button
                        type="button"
                        className={feedback[message.id] === "not_helpful" ? "active" : ""}
                        aria-label="Tandai jawaban tidak membantu"
                        aria-pressed={feedback[message.id] === "not_helpful"}
                        onClick={() => void handleFeedback(message, "not_helpful")}
                      >
                        <ThumbsDownIcon className="icon" />
                      </button>
                    </div>
                  </div>
                </article>
              )
            )}
          </div>
        )}

        {isLoading ? (
          <div className="answer-skeleton" role="status" aria-live="polite">
            <span className="spinner" />
            <div>
              <strong>Menelusuri regulasi yang relevan…</strong>
              <span>Memeriksa pasal, status, dan sumber pendukung.</span>
            </div>
          </div>
        ) : null}
        {error ? (
          <div className="state-strip error" role="alert">
            <AlertIcon className="icon" />
            <span>{error}</span>
          </div>
        ) : null}
        <div ref={conversationEndRef} />

        <form
          className="question-box"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <label htmlFor="question-input">Ketik pertanyaan Anda</label>
          <textarea
            ref={inputRef}
            id="question-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
            placeholder="Contoh: Kapan THR wajib dibayarkan?"
            maxLength={2000}
            rows={2}
            disabled={isLoading}
          />
          <span>Ctrl + Enter untuk kirim · {question.length}/2000</span>
          <div className="composer-actions">
            {isLoading ? (
              <button className="stop-button" type="button" onClick={stopRequest}>
                <StopIcon className="icon" />
                <span>Batalkan</span>
              </button>
            ) : (
              <button className="send-button" type="submit" disabled={!question.trim()}>
                <SendIcon className="icon" />
                <span>Kirim pertanyaan</span>
              </button>
            )}
          </div>
        </form>
        <p className="chat-disclaimer">
          Informasi bersifat edukatif. Selalu periksa sumber resmi sebelum mengambil keputusan.
        </p>
      </section>
      <SourceSheet
        open={isSourceSheetOpen}
        citations={citations}
        question={citationQuestion}
        onClose={closeSourceSheet}
      />
    </AppShell>
  );
}
