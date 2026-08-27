"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

import { AuthModal } from "./auth-modal";
import {
  FileText,
  LogOut,
  Menu,
  PanelLeftClose,
  Pencil,
  Plus,
  Search,
  Scale,
  Settings,
  User,
  X,
} from "lucide-react";
import { ConversationHistory } from "./conversation-history";
import { SettingsModal } from "./settings-modal";
import { useStoredSession } from "@/hooks/use-stored-session";
import { useSettings } from "./settings-provider";
import { SESSION_STORAGE_KEY } from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";

type ChatWorkspaceShellProps = {
  children: ReactNode;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  historyLoading: boolean;
  sidebarExpanded: boolean;
  mobileSidebarOpen: boolean;
  sourceDrawerOpen: boolean;
  sourcePanel?: ReactNode;
  onSidebarExpandedChange: (expanded: boolean) => void;
  onMobileSidebarOpenChange: (open: boolean) => void;
  onSourceDrawerClose: () => void;
  onConversationSelect: (id: string) => void;
  onNewConversation: () => void;
  onConversationRename: (id: string, title: string) => Promise<void>;
  onConversationDelete: (id: string) => Promise<void>;
};

export function ChatWorkspaceShell({
  children,
  conversations,
  activeConversationId,
  historyLoading,
  sidebarExpanded,
  mobileSidebarOpen,
  sourceDrawerOpen,
  sourcePanel,
  onSidebarExpandedChange,
  onMobileSidebarOpenChange,
  onSourceDrawerClose,
  onConversationSelect,
  onNewConversation,
  onConversationRename,
  onConversationDelete,
}: ChatWorkspaceShellProps) {
  const session = useStoredSession();
  const { t: translate } = useSettings();
  const mobileSidebarRef = useRef<HTMLElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const sourceCloseRef = useRef<HTMLButtonElement>(null);
  const authTriggerRef = useRef<HTMLElement | null>(null);
  const profileTriggerRef = useRef<HTMLButtonElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const chatSearchInputRef = useRef<HTMLInputElement>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [chatSearchOpen, setChatSearchOpen] = useState(false);
  const [chatSearchQuery, setChatSearchQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const visibleConversations = chatSearchQuery.trim()
    ? conversations.filter((conversation) =>
        conversation.title
          .toLocaleLowerCase("id-ID")
          .includes(chatSearchQuery.trim().toLocaleLowerCase("id-ID"))
      )
    : conversations;

  function openChatSearch(trigger: HTMLElement) {
    if (!session) {
      openAuthModal(trigger);
      return;
    }
    onSidebarExpandedChange(true);
    setChatSearchOpen(true);
    window.setTimeout(() => chatSearchInputRef.current?.focus(), 0);
  }

  function openAuthModal(trigger: HTMLElement, mode: "login" | "signup" = "login") {
    authTriggerRef.current = trigger;
    setAuthMode(mode);
    onMobileSidebarOpenChange(false);
    setAuthModalOpen(true);
  }

  function closeAuthModal() {
    setAuthModalOpen(false);
    window.setTimeout(() => authTriggerRef.current?.focus(), 0);
  }

  function handleLogout() {
    setProfileMenuOpen(false);
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    window.dispatchEvent(new Event("kerjapedia-session-change"));
    onNewConversation();
    onSourceDrawerClose();
    onMobileSidebarOpenChange(false);
  }

  useEffect(() => {
    if (!profileMenuOpen) return;
    window.setTimeout(
      () => profileMenuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus(),
      0
    );
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (
        !profileMenuRef.current?.contains(target) &&
        !profileTriggerRef.current?.contains(target)
      ) {
        setProfileMenuOpen(false);
      }
    }
    function handleProfileEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setProfileMenuOpen(false);
      window.setTimeout(() => profileTriggerRef.current?.focus(), 0);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleProfileEscape);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleProfileEscape);
    };
  }, [profileMenuOpen]);

  useEffect(() => {
    if (!mobileSidebarOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    mobileCloseRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileSidebarOpen]);

  useEffect(() => {
    if (sourceDrawerOpen) sourceCloseRef.current?.focus();
  }, [sourceDrawerOpen]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (mobileSidebarOpen) {
        onMobileSidebarOpenChange(false);
        window.setTimeout(() => mobileMenuRef.current?.focus(), 0);
      } else if (sourceDrawerOpen) {
        onSourceDrawerClose();
      }
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [mobileSidebarOpen, onMobileSidebarOpenChange, onSourceDrawerClose, sourceDrawerOpen]);

  function keepMobileFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = mobileSidebarRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const historyWrapperClass = `min-h-0 flex-1 [&_aside]:flex [&_aside]:min-h-0 [&_aside]:flex-1 [&_aside]:overflow-y-auto [&_aside]:bg-transparent [&_aside]:border-0 [&_aside]:p-0 [&_aside>div]:mt-0 ${
    session
      ? "[&_h2]:mx-2.5 [&_h2]:mb-2 [&_h2]:font-sans [&_h2]:text-[10px] [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-[0.04em] [&_h2]:text-[#718078]"
      : "[&_h2]:hidden"
  }`;

  const sidebarBody = (
    <>
      <div className="flex min-h-11 items-center justify-between pb-2.5">
        {session ? (
          <Link
            href="/chat"
            className="flex min-w-0 flex-1 items-center gap-2 rounded-[9px] px-1 text-tinta transition hover:bg-[#e9efeb]"
            aria-label="KerjaPedia AI beranda"
          >
            <Scale className="size-[23px]" />
            <strong className="whitespace-nowrap font-display text-sm font-semibold">
              KerjaPedia AI
            </strong>
          </Link>
        ) : (
          <Link
            href="/"
            className="grid size-10 place-items-center rounded-[9px] text-tinta transition hover:bg-[#e9efeb]"
            aria-label="KerjaPedia AI beranda"
          >
            <Scale className="size-[23px]" />
          </Link>
        )}
        <div className="flex flex-none items-center gap-0.5">
          <button
            type="button"
            className="grid size-[38px] place-items-center rounded-lg text-[#48534d] transition hover:bg-[#e9efeb]"
            aria-label="Cari chat"
            aria-expanded={chatSearchOpen}
            onClick={(event) => openChatSearch(event.currentTarget)}
          >
            <Search className="size-5" />
          </button>
          <button
            type="button"
            className="grid size-[38px] place-items-center rounded-lg text-[#48534d] transition hover:bg-[#e9efeb] max-[760px]:hidden"
            aria-label="Tutup sidebar"
            onClick={() => onSidebarExpandedChange(false)}
          >
            <PanelLeftClose className="size-5" />
          </button>
          <button
            type="button"
            className="grid size-[38px] place-items-center rounded-lg text-[#48534d] transition hover:bg-[#e9efeb] hidden max-[760px]:grid"
            ref={mobileCloseRef}
            aria-label="Tutup riwayat"
            onClick={() => {
              onMobileSidebarOpenChange(false);
              window.setTimeout(() => mobileMenuRef.current?.focus(), 0);
            }}
          >
            <X className="size-5" />
          </button>
        </div>
      </div>
      {chatSearchOpen ? (
        <div className="relative mb-2 mt-1 grid min-h-[42px] grid-cols-[20px_minmax(0,1fr)_34px] items-center gap-[7px] rounded-[9px] border border-[#bdc9c2] bg-white py-0 pl-2.5 pr-[3px]">
          <Search className="size-[17px]" />
          <label htmlFor="sidebar-chat-search" className="sr-only">
            Cari chat
          </label>
          <input
            ref={chatSearchInputRef}
            id="sidebar-chat-search"
            type="search"
            placeholder="Cari chat..."
            value={chatSearchQuery}
            onChange={(event) => setChatSearchQuery(event.target.value)}
            className="min-w-0 bg-transparent text-[11px] text-tinta outline-none placeholder:text-[#8a928d]"
          />
          <button
            type="button"
            aria-label="Tutup pencarian chat"
            onClick={() => {
              setChatSearchOpen(false);
              setChatSearchQuery("");
            }}
            className="grid size-[34px] place-items-center rounded-md text-[#637168] transition hover:bg-[#edf2ef]"
          >
            <X className="size-4" />
          </button>
        </div>
      ) : null}
      <nav
        className={`grid gap-[3px] ${session ? "border-b border-[#dce4df] pb-3.5" : ""}`}
        aria-label={session ? "Navigasi pengguna" : "Navigasi guest"}
      >
        <button
          type="button"
          className="flex min-h-11 items-center gap-[11px] rounded-lg bg-[#e8eeea] px-2.5 text-left text-xs font-semibold text-tinta transition hover:bg-[#e3ebe6]"
          onClick={() => {
            onNewConversation();
            onMobileSidebarOpenChange(false);
          }}
        >
          <Plus className="size-[18px]" />
          <span>Chat baru</span>
        </button>
        <Link
          href="/search"
          className="flex min-h-11 items-center gap-[11px] rounded-lg px-2.5 text-xs text-tinta transition hover:bg-[#e3ebe6]"
        >
          <Search className="size-[18px]" />
          <span>Cari Regulasi</span>
        </Link>
        <Link
          href="/legal/disclaimer"
          className="flex min-h-11 items-center gap-[11px] rounded-lg px-2.5 text-xs text-tinta transition hover:bg-[#e3ebe6]"
        >
          <FileText className="size-[18px]" />
          <span>Legal &amp; Bantuan</span>
        </Link>
      </nav>
      {!session ? <div className="min-h-7 flex-1" /> : null}
      <div className={historyWrapperClass}>
        <ConversationHistory
          conversations={visibleConversations}
          activeConversationId={activeConversationId}
          loading={historyLoading}
          onConversationSelect={(id) => {
            onConversationSelect(id);
            onMobileSidebarOpenChange(false);
          }}
          onNewConversation={() => {
            onNewConversation();
            onMobileSidebarOpenChange(false);
          }}
          onConversationRename={onConversationRename}
          onConversationDelete={onConversationDelete}
          historyEnabled={Boolean(session)}
          showNewConversation={false}
          emptyMessage={
            chatSearchQuery.trim()
              ? `Tidak ada chat yang cocok dengan “${chatSearchQuery.trim()}”.`
              : undefined
          }
        />
      </div>
      {session ? (
        <div className="mt-2 border-t border-[#dce4df] pt-2">
          <button
            ref={profileTriggerRef}
            type="button"
            className="flex min-h-11 w-full items-center gap-[11px] rounded-lg px-2.5 text-left text-xs text-tinta transition hover:bg-[#e7eeea]"
            aria-label={`Buka menu profil ${session.user.name}`}
            aria-haspopup="menu"
            aria-expanded={profileMenuOpen}
            onClick={() => setProfileMenuOpen((open) => !open)}
          >
            <span className="grid size-[30px] shrink-0 place-items-center rounded-full bg-javanese text-[10px] font-bold text-white">
              {session.user.name.slice(0, 2).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <strong className="block truncate text-xs font-medium">
                {session.user.name}
              </strong>
              <small className="mt-0.5 block text-[9px] text-muted-text">
                {session.user.roles.join(", ")}
              </small>
            </span>
          </button>
        </div>
      ) : null}
      {!session ? (
        <div className="mt-auto border-t border-[#e8e4dc]">
          <nav className="grid gap-0.5 p-2" aria-label="Menu tamu">
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-[13px] text-tinta transition hover:bg-[#f0f2f0]"
            >
              <span className="flex size-5 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-[18px]">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </span>
              <span>{translate("sidebar.settings")}</span>
            </button>
            <Link
              href="/legal/disclaimer"
              className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-[13px] text-tinta transition hover:bg-[#f0f2f0]"
            >
              <span className="flex size-5 shrink-0 items-center justify-center">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-[18px]">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <path d="M12 17h.01" />
                </svg>
              </span>
              <span className="flex-1">{translate("sidebar.help")}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4 text-[#8a928d]">
                <path d="M15 3h6v6M10 14L21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              </svg>
            </Link>
          </nav>
          <div className="border-t border-[#e8e4dc] p-4">
            <h3 className="text-[15px] font-semibold text-tinta">
              {translate("sidebar.loginTitle")}
            </h3>
            <p className="mt-1 text-[13px] leading-[1.5] text-muted-text">
              {translate("sidebar.loginDescription")}
            </p>
            <button
              type="button"
              className="mt-3 flex min-h-[40px] w-full items-center justify-center rounded-full border border-[#dce4df] bg-white text-[13px] font-semibold text-tinta transition hover:border-javanese hover:bg-[#f5f8f6]"
              onClick={(event) => openAuthModal(event.currentTarget, "login")}
            >
              {translate("sidebar.loginButton")}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );

  const profileMenu = session ? (
    <div
      ref={profileMenuRef}
      role="menu"
      aria-label="Menu profil pengguna"
      className="fixed bottom-16 left-2.5 z-30 w-[min(248px,calc(100vw-24px))] rounded-[14px] border border-[#424743] bg-[#303330] p-2 text-[#f7f9f8] shadow-[0_18px_44px_rgba(16,24,19,0.22)]"
    >
      <div className="flex min-h-[50px] items-center gap-2.5 px-2 pb-2.5 pt-1">
        <span className="grid size-[30px] shrink-0 place-items-center rounded-full bg-[#2cbf91] text-[9px] font-bold text-white">
          {session.user.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <strong className="block text-xs font-semibold">{session.user.name}</strong>
          <small className="mt-[3px] block text-[10px] capitalize text-[#b9c0bc]">
            {session.user.roles.join(", ")}
          </small>
        </div>
      </div>
      <div className="grid gap-0.5 border-t border-[#4d524e] py-[7px]">
        <button
          type="button"
          role="menuitem"
          className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
          onClick={() => {
            onSidebarExpandedChange(true);
            setProfileMenuOpen(false);
          }}
        >
          <User className="size-[18px]" />
          <span>Profil &amp; riwayat</span>
        </button>
        <Link
          href="/search"
          role="menuitem"
          className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
          onClick={() => setProfileMenuOpen(false)}
        >
          <Search className="size-[18px]" />
          <span>Cari Regulasi</span>
        </Link>
        <Link
          href="/legal/privacy"
          role="menuitem"
          className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
          onClick={() => setProfileMenuOpen(false)}
        >
          <Settings className="size-[18px]" />
          <span>Privasi</span>
        </Link>
        {session.user.roles.includes("admin") ? (
          <Link
            href="/admin/settings"
            role="menuitem"
            className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
            onClick={() => setProfileMenuOpen(false)}
          >
<Settings className="size-[18px]" />
            <span>Pengaturan</span>
          </Link>
        ) : null}
      </div>
      <div className="grid gap-0.5 border-t border-[#4d524e] py-[7px]">
          <Link
          href="/legal/disclaimer"
          role="menuitem"
          className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
          onClick={() => setProfileMenuOpen(false)}
        >
          <FileText className="size-[18px]" />
          <span>{translate("sidebar.help")}</span>
        </Link>
        <button
          type="button"
          role="menuitem"
          className="flex min-h-[38px] items-center gap-[11px] rounded-lg px-2.5 text-left text-xs transition hover:bg-[#414541]"
          onClick={handleLogout}
        >
          <LogOut className="size-[18px]" />
          <span>{translate("sidebar.logout")}</span>
        </button>
      </div>
    </div>
  ) : null;

  const collapsedRail = (
    <nav
      className="flex min-h-0 flex-1 flex-col items-center gap-[3px]"
      aria-label="Navigasi sidebar ringkas"
    >
      <Link
        href="/"
        className="mb-2 grid size-11 place-items-center rounded-[10px] text-[#28342d] transition hover:bg-[#e7eeea]"
        aria-label="KerjaPedia AI beranda"
      >
        <Scale className="size-[21px]" />
      </Link>
      <button
        type="button"
        className={`grid size-11 place-items-center rounded-[10px] transition ${
          !activeConversationId
            ? "bg-[#1a1a1a] text-white"
            : "text-[#28342d] hover:bg-[#e7eeea]"
        }`}
        aria-label={translate("sidebar.newChat")}
        onClick={onNewConversation}
      >
        <Pencil className="size-[21px]" />
      </button>
      <button
        type="button"
        className="grid size-11 place-items-center rounded-[10px] text-[#28342d] transition hover:bg-[#e7eeea]"
        aria-label={translate("sidebar.search")}
        onClick={(event) => openChatSearch(event.currentTarget)}
      >
        <Search className="size-[21px]" />
      </button>
      <Link
        href="/legal/disclaimer"
        className="grid size-11 place-items-center rounded-[10px] text-[#28342d] transition hover:bg-[#e7eeea]"
        aria-label={translate("sidebar.legal")}
      >
        <FileText className="size-[21px]" />
      </Link>
      <button
        type="button"
        className="mt-auto grid size-11 place-items-center rounded-[10px] text-[#28342d] transition hover:bg-[#e7eeea]"
        aria-label={session ? translate("sidebar.profile") : translate("sidebar.login")}
        onClick={(event) => {
          if (session) {
            onSidebarExpandedChange(true);
          } else {
            openAuthModal(event.currentTarget);
          }
        }}
      >
        <User className="size-[21px]" />
      </button>
    </nav>
  );

  const shellColumns = !sidebarExpanded
    ? sourceDrawerOpen
      ? "grid-cols-[64px_minmax(0,1fr)_minmax(340px,390px)] max-[1180px]:grid-cols-[64px_minmax(0,1fr)_340px]"
      : "grid-cols-[64px_minmax(0,1fr)]"
    : sourceDrawerOpen
      ? "grid-cols-[268px_minmax(0,1fr)_minmax(340px,390px)] max-[1180px]:grid-cols-[220px_minmax(0,1fr)_340px]"
      : "grid-cols-[268px_minmax(0,1fr)]";

  const topbarColumns = session
    ? "grid-cols-[44px_minmax(0,1fr)_44px] max-[760px]:grid-cols-[44px_34px_minmax(0,1fr)_44px]"
    : "grid-cols-[44px_minmax(0,1fr)_auto] max-[760px]:grid-cols-[44px_34px_minmax(0,1fr)_auto]";

  return (
    <div
      className={[
        "grid h-svh w-full overflow-hidden bg-arsip text-tinta transition-[grid-template-columns] duration-200 max-[760px]:block max-[760px]:h-svh",
        shellColumns,
        session ? "authenticated-shell" : "guest-shell",
      ].join(" ")}
    >
      {sidebarExpanded ? (
        <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-[#dce4df] bg-[#f6faf9] p-[14px_12px_12px] max-[760px]:hidden">
          {sidebarBody}
        </aside>
      ) : (
        <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-[#dce4df] bg-[#f6faf9] p-[14px_8px_12px] max-[760px]:hidden">
          {collapsedRail}
        </aside>
      )}
      <div className="relative flex min-h-0 min-w-0 flex-col bg-white max-[760px]:h-full">
        <header
          className={`relative z-[5] grid min-h-[58px] items-center gap-2 border-b border-[#dce4df] bg-white/95 px-3.5 py-1.5 backdrop-blur-xl ${topbarColumns}`}
        >
          <button
            type="button"
            className={`grid size-11 place-items-center rounded-[9px] text-[#48534d] transition hover:bg-[#e9efeb] max-[760px]:hidden ${
              sidebarExpanded ? "invisible pointer-events-none" : ""
            }`}
            aria-label={sidebarExpanded ? "Tutup sidebar" : "Buka sidebar"}
            aria-expanded={sidebarExpanded}
            aria-hidden={sidebarExpanded}
            tabIndex={sidebarExpanded ? -1 : 0}
            onClick={() => onSidebarExpandedChange(!sidebarExpanded)}
          >
            <PanelLeftClose className="size-[21px]" />
          </button>
          <button
            ref={mobileMenuRef}
            type="button"
            className="hidden size-11 place-items-center rounded-[9px] text-[#48534d] transition hover:bg-[#e9efeb] max-[760px]:grid"
            aria-label={session ? "Buka riwayat" : "Buka menu"}
            aria-expanded={mobileSidebarOpen}
            onClick={() => onMobileSidebarOpenChange(true)}
          >
            <Menu className="size-[21px]" />
          </button>
          <div className="hidden max-[760px]:block">
            <span className="grid size-[30px] place-items-center rounded-[7px] bg-javanese text-[9px] font-bold tracking-[0.04em] text-white">
              KP
            </span>
          </div>
          <h1
            className={`m-0 truncate text-[13px] font-medium text-tinta ${
              session ? "" : "max-[760px]:hidden"
            }`}
          >
            KerjaPedia AI
          </h1>
          {!session ? (
            <div className="flex items-center justify-self-end gap-2 max-[760px]:gap-1.5">
              <button
                type="button"
                className="inline-flex min-h-[38px] items-center justify-center rounded-full border border-[#c8d2cc] bg-white px-4 text-xs font-semibold text-[#253029] transition hover:border-[#9dafa4] hover:bg-[#f7faf8] max-[760px]:min-h-9 max-[760px]:px-[11px] max-[760px]:text-[10px]"
                onClick={(event) => openAuthModal(event.currentTarget, "login")}
              >
                {translate("header.login")}
              </button>
              <button
                type="button"
                className="inline-flex min-h-[38px] items-center justify-center rounded-full border border-[#c8d2cc] bg-white px-4 text-xs font-semibold text-[#253029] transition hover:border-[#9dafa4] hover:bg-[#f7faf8] max-[760px]:min-h-9 max-[760px]:px-[11px] max-[760px]:text-[10px]"
                onClick={(event) => openAuthModal(event.currentTarget, "signup")}
              >
                {translate("header.signup")}
              </button>
            </div>
          ) : null}
        </header>
        {session && profileMenuOpen ? profileMenu : null}
        <main className="min-h-0 flex-1 overflow-hidden bg-white max-[760px]:h-full">
          {children}
        </main>
      </div>
      {sourceDrawerOpen && sourcePanel ? (
        <aside
          className="min-h-0 min-w-0 overflow-auto border-l border-[#dce4df] bg-white max-[760px]:hidden"
          aria-label="Sumber dan kutipan"
        >
          <header className="sticky top-0 z-[3] flex min-h-[58px] items-center justify-between border-b border-[#dce4df] bg-white py-1.5 pl-[26px] pr-[18px]">
            <h2 className="m-0 text-[15px] font-semibold text-tinta">Sumber</h2>
            <button
              ref={sourceCloseRef}
              type="button"
              className="grid size-[38px] place-items-center rounded-lg text-[#48534d] transition hover:bg-[#e9efeb]"
              aria-label="Tutup sumber"
              onClick={onSourceDrawerClose}
            >
<X className="size-5" />
            </button>
          </header>
          {sourcePanel}
        </aside>
      ) : null}
      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-[120]">
          <button
            type="button"
            className="absolute inset-0 w-full border-0 bg-[rgba(18,29,23,0.48)]"
            aria-label={session ? "Tutup riwayat" : "Tutup menu"}
            onClick={() => onMobileSidebarOpenChange(false)}
          />
          <aside
            ref={mobileSidebarRef}
            role="dialog"
            aria-modal="true"
            aria-label={session ? "Riwayat percakapan" : "Menu KerjaPedia"}
            onKeyDown={keepMobileFocusInside}
            className="relative z-[1] flex h-full w-[min(86vw,320px)] flex-col overflow-hidden bg-[#f6faf9] p-[14px_12px_12px] shadow-[16px_0_40px_rgba(17,36,26,0.18)]"
          >
            {sidebarBody}
          </aside>
        </div>
      ) : null}
      <AuthModal
        open={authModalOpen}
        mode={authMode}
        onClose={closeAuthModal}
        onSuccess={() => {
          setAuthModalOpen(false);
          onNewConversation();
        }}
      />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
