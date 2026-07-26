"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "./chat-composer";
import type { ChatMessage } from "./chat-types";
import { ChatWorkspaceShell } from "./chat-workspace-shell";
import { ConversationThread } from "./conversation-thread";
import { AlertIcon } from "./icons";
import { SourcePanel } from "./source-panel";
import { SourceSheet } from "./source-sheet";
import { useStoredSession } from "@/hooks/use-stored-session";
import {
  askQuestionStream,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  renameConversation,
  submitFeedback,
} from "@/lib/api";
import type { AnswerPayload, Citation, ConversationSummary } from "@/lib/types";

const suggestions = [
  "Kapan batas waktu pembayaran THR?",
  "Apakah pekerja PKWT berhak atas uang kompensasi?",
  "Apa syarat PHK karena efisiensi perusahaan?",
];

const SIDEBAR_STORAGE_KEY = "kerjapedia.chat.sidebar.v1";

export function EditorialChatExperience() {
  const session = useStoredSession();
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationQuestion, setCitationQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [isSourceSheetOpen, setIsSourceSheetOpen] = useState(false);
  const [isSourceDrawerOpen, setIsSourceDrawerOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "helpful" | "not_helpful">>({});
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const sourceTriggerRef = useRef<HTMLElement | null>(null);
  const streamingMessageRef = useRef<string | null>(null);

  const closeSourceSheet = useCallback(() => {
    setIsSourceSheetOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, []);
  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setConversations(await fetchConversations(signal));
  }, []);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    async function loadHistory() {
      try {
        const nextConversations = await fetchConversations(controller.signal);
        setConversations(nextConversations);
      } catch (err) {
        if ((err as Error).name !== "AbortError") setError("Riwayat belum dapat dimuat.");
      } finally {
        setHistoryLoading(false);
      }
    }
    void loadHistory();
    return () => controller.abort();
  }, [session]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsSidebarExpanded(window.localStorage.getItem(SIDEBAR_STORAGE_KEY) !== "collapsed");
    }, 0);
    return () => window.clearTimeout(timer);
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
    const messageId = streamingMessageRef.current;
    if (messageId) {
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId ? { ...message, streaming: false, status: undefined } : message
        )
      );
    }
    streamingMessageRef.current = null;
    setIsLoading(false);
    setError("Respons dihentikan. Anda dapat melanjutkan dengan pertanyaan baru.");
  }
  function showSources(answer: AnswerPayload) {
    sourceTriggerRef.current = document.activeElement as HTMLElement | null;
    setCitations(answer.citations);
    setCitationQuestion(answer.query);
    setIsMobileSidebarOpen(false);
    if (window.matchMedia("(max-width: 760px)").matches) {
      setIsSourceSheetOpen(true);
      setIsSourceDrawerOpen(false);
    } else {
      setIsSourceDrawerOpen(true);
    }
  }
  async function handleConversationSelect(nextId: string) {
    if (isLoading || nextId === conversationId) return;
    setError(null);
    setHistoryLoading(true);
    try {
      const detail = await fetchConversation(nextId);
      const nextMessages = detail.messages.flatMap<ChatMessage>((message, index) => {
        if (message.role !== "user" && message.role !== "assistant") return [];
        return [
          {
            id: `${detail.conversation_id}-${index}`,
            role: message.role,
            content: message.content,
            answer: message.metadata.answer,
            createdAt: message.created_at,
          },
        ];
      });
      const latest = [...nextMessages].reverse().find((item) => item.answer)?.answer;
      setConversationId(detail.conversation_id);
      setMessages(nextMessages);
      setCitations(latest?.citations ?? []);
      setCitationQuestion(latest?.query ?? "");
      setIsSourceSheetOpen(false);
      setIsSourceDrawerOpen(false);
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
    setIsSourceDrawerOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }
  async function handleConversationRename(id: string, title: string) {
    setError(null);
    try {
      const updated = await renameConversation(id, title);
      setConversations((current) =>
        current.map((item) => (item.conversation_id === id ? updated : item))
      );
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }
  async function handleConversationDelete(id: string) {
    setError(null);
    try {
      await deleteConversation(id);
      setConversations((current) => current.filter((item) => item.conversation_id !== id));
      if (id === conversationId) handleNewConversation();
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }
  async function handleSubmit(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (!trimmed || isLoading) return;
    setError(null);
    setQuestion("");
    setIsLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const assistantMessageId = crypto.randomUUID();
    streamingMessageRef.current = assistantMessageId;
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        streaming: true,
        status: "Menganalisis pertanyaan",
      },
    ]);
    try {
      const response = await askQuestionStream(trimmed, conversationId, controller.signal, {
        onStart: setConversationId,
        onThinking: (status) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, status } : message
            )
          ),
        onDelta: (content) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? { ...message, content: message.content + content, status: undefined }
                : message
            )
          ),
      });
      setConversationId(response.conversation_id);
      setCitations(response.answer.citations);
      setCitationQuestion(trimmed);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: response.answer.answer,
                answer: response.answer,
                streaming: false,
                status: undefined,
              }
            : message
        )
      );
      await refreshHistory();
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setIsLoading(false);
      abortRef.current = null;
      streamingMessageRef.current = null;
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

  const sourcePanel =
    citations.length > 0 ? (
      <SourcePanel citations={citations} question={citationQuestion} />
    ) : undefined;

  return (
    <ChatWorkspaceShell
      conversations={conversations}
      activeConversationId={conversationId}
      historyLoading={historyLoading}
      sidebarExpanded={isSidebarExpanded}
      mobileSidebarOpen={isMobileSidebarOpen}
      sourceDrawerOpen={isSourceDrawerOpen}
      sourcePanel={sourcePanel}
      onSidebarExpandedChange={(expanded) => {
        setIsSidebarExpanded(expanded);
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, expanded ? "expanded" : "collapsed");
      }}
      onMobileSidebarOpenChange={(open) => {
        setIsMobileSidebarOpen(open);
        if (open) setIsSourceSheetOpen(false);
      }}
      onSourceDrawerClose={() => {
        setIsSourceDrawerOpen(false);
        window.setTimeout(() => sourceTriggerRef.current?.focus(), 0);
      }}
      onConversationSelect={(id) => void handleConversationSelect(id)}
      onNewConversation={handleNewConversation}
      onConversationRename={handleConversationRename}
      onConversationDelete={handleConversationDelete}
    >
      <section className={messages.length === 0 ? "editorial-chat is-empty" : "editorial-chat"}>
        <div className="editorial-conversation-scroll">
          {messages.length === 0 ? (
            <div className="editorial-empty-state">
              <h1>Apa yang ingin Anda pahami?</h1>
              <p>Tanyakan regulasi ketenagakerjaan dan periksa dasar hukumnya.</p>
              <div className="editorial-suggestions">
                {suggestions.map((item) => (
                  <button key={item} type="button" onClick={() => void handleSubmit(item)}>
                    {item}
                    <span aria-hidden="true">→</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ConversationThread
              messages={messages}
              feedback={feedback}
              onShowSources={showSources}
              onFeedback={(message, rating) => void handleFeedback(message, rating)}
              onEditMessage={(message) => {
                setQuestion(message.content);
                window.setTimeout(() => inputRef.current?.focus(), 0);
              }}
            />
          )}
          {isLoading && !messages.some((message) => message.streaming) ? (
            <div className="editorial-loading" role="status" aria-live="polite">
              <span className="spinner" />
              <div>
                <strong>Menelusuri regulasi yang relevan…</strong>
                <span>Memeriksa pasal, status, dan sumber pendukung.</span>
              </div>
            </div>
          ) : null}
          {error ? (
            <div className="editorial-error" role="alert">
              <AlertIcon className="icon" />
              <span>{error}</span>
            </div>
          ) : null}
          <div ref={conversationEndRef} />
        </div>
        <ChatComposer
          question={question}
          loading={isLoading}
          inputRef={inputRef}
          onQuestionChange={setQuestion}
          onSubmit={() => void handleSubmit()}
          onCancel={stopRequest}
        />
        {messages.length === 0 ? (
          <p className="guest-legal-note">
            KerjaPedia dapat membuat kekeliruan. Periksa selalu sumber resmi. Dengan menggunakan
            layanan ini, Anda menyetujui <Link href="/legal/terms">Ketentuan</Link>,{" "}
            <Link href="/legal/privacy">Privasi</Link>, dan{" "}
            <Link href="/legal/disclaimer">Disclaimer</Link>.
          </p>
        ) : null}
      </section>
      <SourceSheet
        open={isSourceSheetOpen}
        citations={citations}
        question={citationQuestion}
        onClose={closeSourceSheet}
      />
    </ChatWorkspaceShell>
  );
}
