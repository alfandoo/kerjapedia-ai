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
      <section className="mx-auto flex w-full max-w-[860px] flex-1 flex-col gap-3 px-6 pt-16 pb-10 max-[760px]:px-4 max-[760px]:pt-10">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-javanese/10 text-javanese">
            <ChatIcon className="size-[18px] [stroke-width:1.8]" />
          </span>
          <div>
            <span className="text-[10px] font-bold tracking-[0.18em] text-forest uppercase">
              Asisten regulasi ketenagakerjaan
            </span>
            <h1 className="mt-1 font-display text-[26px] leading-tight font-semibold text-tinta">
              Tanyakan hak kerja Anda dengan sumber yang jelas
            </h1>
            <p className="mt-1.5 text-sm leading-[1.6] text-muted-text">
              Jawaban dirangkum dari dokumen resmi dan selalu dapat Anda periksa kembali.
            </p>
          </div>
        </div>

        {messages.length === 0 ? (
          <div className="mt-6 flex flex-col items-center gap-3">
            <div className="inline-flex items-center gap-2.5 rounded-full border border-[#dce4df] bg-[#f6faf9] px-4 py-2.5 text-xs text-[#26312b]">
              <strong className="font-semibold text-javanese">
                Jawaban berbasis dokumen, bukan tebakan.
              </strong>
              <span className="text-muted-text">
                KerjaPedia akan menolak jika sumber yang tersedia tidak cukup.
              </span>
            </div>
            <p className="text-sm text-muted-text">Mulai dengan salah satu pertanyaan berikut:</p>
            <div className="grid w-full max-w-[520px] gap-2.5">
              {suggestions.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="flex min-h-[46px] cursor-pointer items-center gap-2.5 rounded-lg border border-[#dce4df] bg-white px-3.5 text-left text-[13px] text-[#26312b] transition hover:border-[#9adbd5] hover:bg-[#f6faf9] hover:text-javanese"
                  onClick={() => void handleSubmit(item)}
                >
                  <ChatIcon className="size-[18px] [stroke-width:1.8] shrink-0 text-javanese" />
                  <span>{item}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-5" aria-live="polite" aria-label="Percakapan">
            {messages.map((message) =>
              message.role === "user" ? (
                <div className="flex justify-end" key={message.id}>
                  <p className="max-w-[min(78%,560px)] rounded-[18px_18px_4px_18px] bg-[#eef4f0] px-4 py-[11px] text-[13px] leading-[1.55] text-[#29332d]">
                    {message.content}
                  </p>
                </div>
              ) : (
                <article
                  className="rounded-xl border border-[#f1e3c0] border-l-[3px] border-l-emas bg-white p-5"
                  key={message.id}
                >
                  <div className="flex items-center gap-2">
                    <span className="grid size-7 place-items-center rounded-full bg-javanese text-[10px] font-bold text-white">
                      KP
                    </span>
                    <span className="text-xs font-semibold text-tinta">Jawaban KerjaPedia</span>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-[1.8] text-tinta">
                    {message.content}
                  </p>
                  {message.answer?.citations.length ? (
                    <button
                      className="mt-3 inline-flex min-h-[34px] cursor-pointer items-center gap-2 text-xs font-semibold text-javanese transition hover:text-forest"
                      type="button"
                      onClick={() => showSources(message.answer as AnswerPayload)}
                    >
                      Lihat {message.answer.citations.length} sumber resmi
                      <span aria-hidden="true">→</span>
                    </button>
                  ) : null}
                  {message.answer?.refusal_reason ? (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border-l-[3px] border-[#bd8a2e] bg-[#fffaf0] p-3 text-xs leading-[1.55] text-[#88540d]">
                      <AlertIcon className="size-[18px] [stroke-width:1.8] shrink-0" />
                      <span>
                        Dasar dokumen belum cukup untuk menjawab pertanyaan ini dengan aman.
                      </span>
                    </div>
                  ) : null}
                  {message.answer?.clarification_question ? (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border-l-[3px] border-[#bd8a2e] bg-[#fffaf0] p-3 text-xs leading-[1.55] text-[#88540d]">
                      <AlertIcon className="size-[18px] [stroke-width:1.8] shrink-0" />
                      <span>{message.answer.clarification_question}</span>
                    </div>
                  ) : null}
                  <div className="mt-3 flex items-center justify-between gap-3 border-t border-[#edf1ee] pt-2.5">
                    <span className="text-[11px] text-muted-text">Apakah jawaban ini membantu?</span>
                    <div className="flex gap-1">
                      <button
                        type="button"
                        className={`grid size-8 place-items-center rounded-lg border transition ${
                          feedback[message.id] === "helpful"
                            ? "border-[#afc9bb] bg-[#f5f8f6] text-javanese"
                            : "border-transparent text-[#68736c] hover:bg-[#eef2ef] hover:text-[#26312b]"
                        }`}
                        aria-label="Tandai jawaban membantu"
                        aria-pressed={feedback[message.id] === "helpful"}
                        onClick={() => void handleFeedback(message, "helpful")}
                      >
                        <ThumbsUpIcon className="size-[18px] [stroke-width:1.8]" />
                      </button>
                      <button
                        type="button"
                        className={`grid size-8 place-items-center rounded-lg border transition ${
                          feedback[message.id] === "not_helpful"
                            ? "border-[#afc9bb] bg-[#f5f8f6] text-javanese"
                            : "border-transparent text-[#68736c] hover:bg-[#eef2ef] hover:text-[#26312b]"
                        }`}
                        aria-label="Tandai jawaban tidak membantu"
                        aria-pressed={feedback[message.id] === "not_helpful"}
                        onClick={() => void handleFeedback(message, "not_helpful")}
                      >
                        <ThumbsDownIcon className="size-[18px] [stroke-width:1.8]" />
                      </button>
                    </div>
                  </div>
                </article>
              )
            )}
          </div>
        )}

        {isLoading ? (
          <div
            className="flex items-center gap-3 rounded-xl border border-[#e8eee8] bg-[#fafbfa] p-4"
            role="status"
            aria-live="polite"
          >
            <span
              className="size-5 shrink-0 rounded-full border-2 border-[#c9d3cb] border-t-javanese [animation:spin_0.9s_linear_infinite]"
              aria-hidden="true"
            />
            <div className="flex flex-col gap-0.5">
              <strong className="text-xs font-semibold text-[#26312b]">
                Menelusuri regulasi yang relevan…
              </strong>
              <span className="text-[11px] text-muted-text">
                Memeriksa pasal, status, dan sumber pendukung.
              </span>
            </div>
          </div>
        ) : null}
        {error ? (
          <div
            className="flex items-start gap-2 rounded-lg border-l-[3px] border-[#c0563f] bg-[#fdf3f1] p-3 text-xs leading-[1.55] text-[#8c3a27]"
            role="alert"
          >
            <AlertIcon className="size-[18px] [stroke-width:1.8] shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}
        <div ref={conversationEndRef} />

        <form
          className="relative rounded-2xl border border-[#dce4df] bg-white p-4 shadow-sm"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <label htmlFor="question-input" className="sr-only">
            Ketik pertanyaan Anda
          </label>
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
            className="w-full resize-none rounded-xl bg-transparent text-sm leading-[1.65] text-tinta outline-none placeholder:text-[#8a928d] disabled:cursor-not-allowed"
          />
          <span className="pointer-events-none text-[10px] font-medium tracking-wide text-[#8a928d]">
            Ctrl + Enter untuk kirim · {question.length}/2000
          </span>
          <div className="mt-3 flex justify-end gap-2">
            {isLoading ? (
              <button
                className="grid h-[38px] cursor-pointer items-center gap-1.5 rounded-xl border border-[#dce4df] bg-white px-3.5 text-xs font-semibold text-[#68736c] transition hover:bg-[#f2f5f2] hover:text-[#26312b]"
                type="button"
                onClick={stopRequest}
              >
                <StopIcon className="size-[18px] [stroke-width:1.8]" />
                <span>Batalkan</span>
              </button>
            ) : (
              <button
                className="grid h-[38px] cursor-pointer items-center gap-1.5 rounded-xl bg-javanese px-3.5 text-xs font-semibold text-white transition hover:bg-forest disabled:cursor-not-allowed disabled:bg-[#c9d3cb]"
                type="submit"
                disabled={!question.trim()}
              >
                <SendIcon className="size-[18px] [stroke-width:1.8]" />
                <span>Kirim pertanyaan</span>
              </button>
            )}
          </div>
        </form>
        <p className="mt-1.5 text-center text-[11px] leading-[1.6] text-muted-text">
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
