"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { deleteConversation, renameConversation } from "@/features/chat/api";
import { ChatWorkspaceShell } from "@/features/chat/components/chat-workspace-shell";
import { useConversationHistory } from "@/features/chat/use-conversation-history";
import { readPreference, writePreference } from "@/lib/preference-cookie";
import { useSettings } from "@/features/settings";

const SIDEBAR_STORAGE_KEY = "kerjapedia.chat.sidebar.v1";

export function ComplianceWorkspace() {
  const router = useRouter();
  const { conversations, setConversations, historyLoading, historyError, retryHistory } =
    useConversationHistory();
  const { t: translate } = useSettings();
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsSidebarExpanded(readPreference(SIDEBAR_STORAGE_KEY) !== "collapsed");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function handleConversationRename(id: string, title: string) {
    const updated = await renameConversation(id, title);
    setConversations((current) =>
      current.map((item) => (item.conversation_id === id ? updated : item))
    );
  }

  async function handleConversationDelete(id: string) {
    await deleteConversation(id);
    setConversations((current) => current.filter((item) => item.conversation_id !== id));
  }

  function handleConversationSelect(id: string) {
    router.push(`/chat?conversation=${encodeURIComponent(id)}`);
  }

  return (
    <ChatWorkspaceShell
      conversations={conversations}
      activeConversationId={null}
      historyLoading={historyLoading}
      historyError={historyError}
      onRetryHistory={retryHistory}
      sidebarExpanded={isSidebarExpanded}
      mobileSidebarOpen={isMobileSidebarOpen}
      sourceDrawerOpen={false}
      onSidebarExpandedChange={(expanded) => {
        setIsSidebarExpanded(expanded);
        writePreference(SIDEBAR_STORAGE_KEY, expanded ? "expanded" : "collapsed");
      }}
      onMobileSidebarOpenChange={setIsMobileSidebarOpen}
      onSourceDrawerClose={() => undefined}
      onConversationSelect={handleConversationSelect}
      onNewConversation={() => router.push("/chat")}
      onConversationRename={handleConversationRename}
      onConversationDelete={handleConversationDelete}
    >
      <div className="mx-auto w-full max-w-[760px] px-[clamp(24px,6vw,92px)] pb-16 pt-[clamp(32px,5vw,64px)] max-[760px]:px-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-javanese">
          {translate("compliance.title")}
        </p>
        <h1 className="font-display text-[clamp(34px,3.5vw,46px)] font-medium leading-[1.12] tracking-[-0.02em] text-javanese-deep">
          {translate("compliance.title")}
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          {translate("compliance.description")}
        </p>

        <div className="mt-8 flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="text-lg font-semibold text-foreground">{translate("compliance.comingSoon")}</p>
          <p className="mt-2 max-w-[480px] text-sm leading-relaxed text-muted-foreground">
            {translate("compliance.note")}
          </p>
        </div>

        <div className="mt-8 flex justify-center">
          <Link
            href="/chat"
            className="inline-flex h-11 items-center rounded-xl border border-input px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-accent"
          >
            {translate("compliance.backToChat")}
          </Link>
        </div>
      </div>
    </ChatWorkspaceShell>
  );
}
