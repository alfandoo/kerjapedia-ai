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

export function KalkulatorWorkspace() {
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
      <div className="mx-auto w-full min-w-0 max-w-[760px] px-[clamp(24px,6vw,92px)] pb-16 pt-[clamp(32px,5vw,64px)] max-[760px]:px-4 max-[760px]:pb-12 max-[760px]:pt-7">
        <h1 className="font-display text-[clamp(34px,3.5vw,46px)] font-medium leading-[1.12] tracking-[-0.02em] text-javanese-deep">
          {translate("kalkulator.title")}
        </h1>
        <p className="mt-4 break-words text-sm leading-relaxed text-muted-foreground">
          {translate("kalkulator.description")}
        </p>

        <div className="mt-8 flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="text-lg font-semibold text-foreground">
            {translate("kalkulator.comingSoon")}
          </p>
          <p className="mt-2 max-w-[480px] break-words text-sm leading-relaxed text-muted-foreground">
            {translate("kalkulator.note")}
          </p>
        </div>

        <div className="mt-8 flex justify-center">
          <Link
            href="/chat"
            className="inline-flex h-11 items-center rounded-xl border border-input px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {translate("kalkulator.backToChat")}
          </Link>
        </div>
      </div>
    </ChatWorkspaceShell>
  );
}
