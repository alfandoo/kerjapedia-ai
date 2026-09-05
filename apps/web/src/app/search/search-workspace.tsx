"use client";

import { readPreference, writePreference } from "@/lib/preference-cookie";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RegulationSearch } from "@/features/documents";
import { deleteConversation, fetchConversations, renameConversation } from "@/features/chat/api";
import { ChatWorkspaceShell } from "@/features/chat/components/chat-workspace-shell";
import type { ConversationSummary } from "@/features/chat/types";
import { useStoredSession } from "@/features/auth";

const SIDEBAR_STORAGE_KEY = "kerjapedia.chat.sidebar.v1";

export function SearchWorkspace() {
  const router = useRouter();
  const session = useStoredSession();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    async function loadHistory() {
      try {
        setConversations(await fetchConversations(controller.signal));
      } catch (err) {
        if ((err as Error).name !== "AbortError") setConversations([]);
      } finally {
        setHistoryLoading(false);
      }
    }
    void loadHistory();
    return () => controller.abort();
  }, [session]);

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
    // Search has no conversation view; route to chat which owns the thread.
    router.push(`/chat?conversation=${encodeURIComponent(id)}`);
  }

  return (
    <ChatWorkspaceShell
      conversations={conversations}
      activeConversationId={null}
      historyLoading={historyLoading}
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
      <div className="h-full min-h-0 overflow-y-auto px-[clamp(24px,6vw,92px)] pb-16 pt-[clamp(32px,5vw,64px)] max-[760px]:px-4 max-[760px]:pb-12 max-[760px]:pt-7">
        <RegulationSearch />
      </div>
    </ChatWorkspaceShell>
  );
}
