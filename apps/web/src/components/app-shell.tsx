"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ChatAppHeader } from "./chat-app-header";
import { ChatIcon, DatabaseIcon, FileIcon, ScaleIcon, SearchIcon } from "./icons";
import { ConversationHistory } from "./conversation-history";
import { useStoredSession } from "@/hooks/use-stored-session";
import type { ConversationSummary } from "@/lib/types";

type AppShellProps = {
  children: ReactNode;
  rightPanel?: ReactNode;
  conversations?: ConversationSummary[];
  activeConversationId?: string | null;
  historyLoading?: boolean;
  onConversationSelect?: (conversationId: string) => void;
  onNewConversation?: () => void;
  editorial?: boolean;
};

function getNavigation(session: { user: { roles: string[] } } | null) {
  const base = [
    { href: "/chat", label: "Chat", icon: ChatIcon },
    { href: "/search", label: "Cari Regulasi", icon: SearchIcon },
  ];
  if (session?.user.roles.includes("admin")) {
    base.push({ href: "/admin", label: "Admin", icon: DatabaseIcon });
  }
  base.push({ href: "/legal/disclaimer", label: "Legal", icon: FileIcon });
  return base;
}

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function AppShell({
  children,
  rightPanel,
  conversations = [],
  activeConversationId,
  historyLoading = false,
  onConversationSelect,
  onNewConversation,
  editorial = false,
}: AppShellProps) {
  const pathname = usePathname();
  const session = useStoredSession();

  if (editorial) {
    return (
      <div className="editorial-shell">
        <ChatAppHeader />
        <div
          className={
            rightPanel
              ? "editorial-workspace editorial-workspace-with-sources"
              : "editorial-workspace"
          }
        >
          <ConversationHistory
            conversations={conversations}
            activeConversationId={activeConversationId}
            loading={historyLoading}
            onConversationSelect={onConversationSelect}
            onNewConversation={onNewConversation}
          />
          <main className="editorial-main">{children}</main>
          {rightPanel ? (
            <aside className="editorial-sources" aria-label="Sumber dan kutipan">
              {rightPanel}
            </aside>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link href="/chat" className="public-brand" aria-label="KerjaPedia AI beranda">
          <span className="public-brand-mark">
            <ScaleIcon className="icon" />
          </span>
          <span>KerjaPedia AI</span>
        </Link>
        <nav className="public-nav" aria-label="Navigasi utama">
          {getNavigation(session).map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "public-nav-item active" : "public-nav-item"}
              >
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <Link href="/login-admin" className="public-session">
          <span className="public-avatar">
            {session ? session.user.name.slice(0, 2).toUpperCase() : "TM"}
          </span>
          <span>
            <strong>{session ? session.user.name : "Tamu"}</strong>
            <small>{session ? session.user.roles.join(", ") : "Belum masuk"}</small>
          </span>
        </Link>
      </header>
      <div className="public-workspace">
        <aside className="history-rail" aria-label="Riwayat percakapan">
          <div className="rail-header">
            <h2>Riwayat</h2>
            <button className="secondary-button" type="button" onClick={onNewConversation}>
              + Percakapan baru
            </button>
          </div>
          <div className="history-list" aria-busy={historyLoading}>
            {historyLoading ? <p className="history-empty">Memuat riwayat…</p> : null}
            {!historyLoading && conversations.length === 0 ? (
              <p className="history-empty">Belum ada percakapan. Ajukan pertanyaan pertama Anda.</p>
            ) : null}
            {conversations.map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                className={
                  item.conversation_id === activeConversationId
                    ? "history-item active"
                    : "history-item"
                }
                aria-current={item.conversation_id === activeConversationId ? "true" : undefined}
                onClick={() => onConversationSelect?.(item.conversation_id)}
              >
                <ChatIcon className="icon" />
                <span>
                  <strong>{item.title}</strong>
                  <small>{formatHistoryTime(item.updated_at)}</small>
                </span>
              </button>
            ))}
          </div>
          <Link href="/search" className="rail-link">
            <SearchIcon className="icon" />
            Lihat semua regulasi
          </Link>
        </aside>
        <main className="public-main">{children}</main>
        <aside className="source-rail" aria-label="Sumber dan kutipan">
          {rightPanel}
        </aside>
      </div>
    </div>
  );
}
