"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ChatAppHeader } from "./chat-app-header";
import { ChatIcon, DatabaseIcon, FileIcon, ScaleIcon, SearchIcon } from "./icons";
import { ConversationHistory } from "./conversation-history";
import { useStoredSession } from "@/hooks/use-stored-session";
import { useSettings } from "./settings-provider";
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
    base.push({ href: "/admin/dashboard", label: "Admin", icon: DatabaseIcon });
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
  const { t: translate } = useSettings();

  if (editorial) {
    return (
      <div className="min-h-[100svh] bg-white text-tinta">
        <ChatAppHeader />
        <div
          className={`grid h-[calc(100svh-78px)] min-h-0 grid-cols-[minmax(230px,19%)_minmax(500px,1fr)] overflow-hidden max-[760px]:block max-[760px]:h-[calc(100svh-100px)] ${
            rightPanel
              ? "min-[1181px]:grid-cols-[minmax(230px,19%)_minmax(500px,1fr)_minmax(330px,27%)]"
              : ""
          }`}
        >
          <ConversationHistory
            conversations={conversations}
            activeConversationId={activeConversationId}
            loading={historyLoading}
            onConversationSelect={onConversationSelect}
            onNewConversation={onNewConversation}
          />
          <main className="min-h-0 min-w-0 overflow-hidden bg-white max-[760px]:h-full">
            {children}
          </main>
          {rightPanel ? (
            <aside
              className="hidden min-h-0 min-w-0 overflow-auto border-l border-[#dce4df] bg-white min-[1181px]:block"
              aria-label="Sumber dan kutipan"
            >
              {rightPanel}
            </aside>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[100svh] bg-white text-tinta">
      <header className="sticky top-0 z-20 grid min-h-[72px] grid-cols-[280px_minmax(0,1fr)_210px] items-center gap-6 border-b border-[#dce4df] bg-white/95 px-7 backdrop-blur-xl max-[900px]:grid-cols-[1fr_auto] max-[900px]:min-h-[112px] max-[900px]:gap-x-4 max-[900px]:gap-y-2 max-[900px]:px-4 max-[900px]:pt-2.5">
        <Link
          href="/chat"
          className="flex w-fit items-center gap-2.5 font-display text-[21px] font-semibold text-tinta max-[900px]:text-lg"
          aria-label="KerjaPedia AI beranda"
        >
          <span className="flex size-[42px] items-center justify-center rounded-[9px] bg-javanese text-emas max-[900px]:size-[38px]">
            <ScaleIcon className="size-[22px] [stroke-width:1.6]" />
          </span>
          <span>KerjaPedia AI</span>
        </Link>
        <nav
          className="flex h-full items-stretch justify-center gap-[34px] max-[900px]:col-span-2 max-[900px]:row-start-2 max-[900px]:h-12 max-[900px]:justify-start max-[900px]:gap-6 max-[900px]:overflow-x-auto"
          aria-label="Navigasi utama"
        >
          {getNavigation(session).map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative grid min-w-11 place-items-center whitespace-nowrap text-[13px] font-medium text-[#5d6862] transition hover:text-javanese max-[900px]:flex-none max-[900px]:text-xs ${
                  active
                    ? "text-forest after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 after:bg-forest"
                    : ""
                }`}
              >
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        {session ? (
          <Link href="/chat" className="flex min-h-11 items-center justify-self-end gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-full bg-javanese text-[11px] font-bold text-white">
              {session.user.name.slice(0, 2).toUpperCase()}
            </span>
            <span className="max-[900px]:hidden">
              <strong className="block text-xs text-tinta">{session.user.name}</strong>
              <small className="mt-0.5 block text-[9px] text-muted-text">
                {session.user.roles.join(", ")}
              </small>
            </span>
          </Link>
        ) : (
          <Link href="/register" className="flex min-h-11 items-center justify-self-end gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-full bg-javanese text-[11px] font-bold text-white">
              TM
            </span>
            <span className="max-[900px]:hidden">
              <strong className="block text-xs text-tinta">Tamu</strong>
              <small className="mt-0.5 block text-[9px] text-muted-text">Masuk / Daftar</small>
            </span>
          </Link>
        )}
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] min-[1181px]:grid-cols-[300px_minmax(0,1fr)_360px]">
        <aside
          className="flex flex-col gap-2.5 border-b border-[#dce4df] bg-white/80 p-4 lg:gap-6 lg:border-b-0 lg:border-r lg:p-6"
          aria-label={translate("sidebar.chatHistory")}
        >
          <div className="flex items-center justify-between gap-4 lg:flex-col lg:items-stretch lg:justify-start">
            <h2 className="text-lg font-bold text-tinta">{translate("sidebar.chatHistory")}</h2>
            <button
              className="h-11 rounded-[7px] border border-[#dce4df] bg-white px-3.5 text-sm font-semibold text-tinta transition hover:border-javanese hover:text-javanese lg:w-full"
              type="button"
              onClick={onNewConversation}
            >
              + {translate("sidebar.newChat")}
            </button>
          </div>
          <div
            className="flex flex-col gap-1.5 max-lg:hidden lg:flex-1"
            aria-busy={historyLoading}
          >
            {historyLoading ? (
              <p className="my-1.5 px-1 text-xs leading-[1.55] text-muted-text">
                {translate("sidebar.loadingHistory")}
              </p>
            ) : null}
            {!historyLoading && conversations.length === 0 ? (
              <p className="my-1.5 px-1 text-xs leading-[1.55] text-muted-text">
                {translate("sidebar.emptyHistory")}
              </p>
            ) : null}
            {conversations.map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                className={`flex min-h-14 w-full items-center gap-2.5 rounded-[7px] border-0 bg-transparent px-3 py-2.5 text-left text-tinta transition hover:translate-x-0.5 hover:bg-[#f6faf9] ${
                  item.conversation_id === activeConversationId
                    ? "bg-[#dff4f1] text-forest"
                    : ""
                }`}
                aria-current={item.conversation_id === activeConversationId ? "true" : undefined}
                onClick={() => onConversationSelect?.(item.conversation_id)}
              >
                <ChatIcon className="size-[18px] shrink-0 [stroke-width:1.8]" />
                <span className="min-w-0">
                  <strong className="block truncate text-[13px] font-bold">{item.title}</strong>
                  <small className="mt-1 block text-xs text-muted-text">
                    {formatHistoryTime(item.updated_at)}
                  </small>
                </span>
              </button>
            ))}
          </div>
          <Link
            href="/search"
            className="hidden items-center justify-center gap-2.5 rounded-[7px] border border-[#dce4df] bg-white text-sm font-semibold text-tinta transition hover:border-javanese hover:text-javanese lg:flex lg:h-11"
          >
            <SearchIcon className="size-[18px] [stroke-width:1.8]" />
            {translate("sidebar.viewAllRegulations")}
          </Link>
        </aside>
        <main className="min-h-[calc(100svh-72px)] min-w-0 bg-white px-[clamp(24px,6vw,92px)] pb-[72px] pt-[clamp(38px,5vw,64px)]">
          {children}
        </main>
        <aside
          className="hidden min-w-0 border-l border-[#dce4df] bg-white/80 px-4 pb-6 min-[1181px]:block"
          aria-label="Sumber dan kutipan"
        >
          {rightPanel}
        </aside>
      </div>
    </div>
  );
}
