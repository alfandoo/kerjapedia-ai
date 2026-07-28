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
import { EditIcon, FileIcon, ScaleIcon, SearchIcon, SettingsIcon, UserIcon } from "./icons";
import { ConversationHistory } from "./conversation-history";
import { useStoredSession } from "@/hooks/use-stored-session";
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

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function PanelIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10 5H5v14h5M14 8l4 4-4 4M9 12h9" />
    </svg>
  );
}

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

  const authenticatedSidebarContent = (
    <>
      <div className="chatgpt-sidebar-heading">
        <Link
          href="/chat"
          className="chatgpt-sidebar-mark chatgpt-sidebar-brand-full"
          aria-label="KerjaPedia AI beranda"
        >
          <ScaleIcon />
          <strong>KerjaPedia AI</strong>
        </Link>
        <div className="chatgpt-sidebar-heading-actions">
          <button
            type="button"
            className="chatgpt-icon-button"
            aria-label="Cari chat"
            aria-expanded={chatSearchOpen}
            onClick={(event) => openChatSearch(event.currentTarget)}
          >
            <SearchIcon />
          </button>
          <button
            type="button"
            className="chatgpt-icon-button desktop-only"
            aria-label="Tutup sidebar"
            onClick={() => onSidebarExpandedChange(false)}
          >
            <PanelIcon />
          </button>
          <button
            type="button"
            className="chatgpt-icon-button mobile-only"
            ref={mobileCloseRef}
            aria-label="Tutup riwayat"
            onClick={() => {
              onMobileSidebarOpenChange(false);
              window.setTimeout(() => mobileMenuRef.current?.focus(), 0);
            }}
          >
            <CloseIcon />
          </button>
        </div>
      </div>
      {chatSearchOpen ? (
        <div className="sidebar-chat-search">
          <SearchIcon />
          <label htmlFor="sidebar-chat-search">Cari chat</label>
          <input
            ref={chatSearchInputRef}
            id="sidebar-chat-search"
            type="search"
            placeholder="Cari chat..."
            value={chatSearchQuery}
            onChange={(event) => setChatSearchQuery(event.target.value)}
          />
          <button
            type="button"
            aria-label="Tutup pencarian chat"
            onClick={() => {
              setChatSearchOpen(false);
              setChatSearchQuery("");
            }}
          >
            <CloseIcon />
          </button>
        </div>
      ) : null}
      <nav className="guest-sidebar-primary" aria-label="Navigasi pengguna">
        <button
          type="button"
          className="guest-new-chat"
          onClick={() => {
            onNewConversation();
            onMobileSidebarOpenChange(false);
          }}
        >
          <PlusIcon />
          <span>Chat baru</span>
        </button>
        <Link href="/search">
          <SearchIcon className="icon" />
          <span>Cari Regulasi</span>
        </Link>
        <Link href="/legal/disclaimer">
          <FileIcon className="icon" />
          <span>Legal &amp; Bantuan</span>
        </Link>
      </nav>
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
      <div className="chatgpt-account">
        <button
          ref={profileTriggerRef}
          type="button"
          className="chatgpt-account-main"
          aria-label={`Buka menu profil ${session?.user.name ?? "pengguna"}`}
          aria-haspopup="menu"
          aria-expanded={profileMenuOpen}
          onClick={() => setProfileMenuOpen((open) => !open)}
        >
          <span className="chatgpt-account-avatar">
            {session ? session.user.name.slice(0, 2).toUpperCase() : "TM"}
          </span>
          <span className="chatgpt-account-identity">
            <strong>{session ? session.user.name : "Tamu"}</strong>
            <small>{session ? session.user.roles.join(", ") : "Belum masuk"}</small>
          </span>
        </button>
      </div>
    </>
  );

  const guestSidebarContent = (
    <>
      <div className="chatgpt-sidebar-heading">
        <Link href="/" className="chatgpt-sidebar-mark" aria-label="KerjaPedia AI beranda">
          <ScaleIcon />
        </Link>
        <div className="chatgpt-sidebar-heading-actions">
          <button
            type="button"
            className="chatgpt-icon-button"
            aria-label="Cari chat"
            onClick={(event) => openChatSearch(event.currentTarget)}
          >
            <SearchIcon />
          </button>
          <button
            type="button"
            className="chatgpt-icon-button desktop-only"
            aria-label="Tutup sidebar"
            onClick={() => onSidebarExpandedChange(false)}
          >
            <PanelIcon />
          </button>
          <button
            type="button"
            className="chatgpt-icon-button mobile-only"
            ref={mobileCloseRef}
            aria-label="Tutup menu"
            onClick={() => {
              onMobileSidebarOpenChange(false);
              window.setTimeout(() => mobileMenuRef.current?.focus(), 0);
            }}
          >
            <CloseIcon />
          </button>
        </div>
      </div>
      <nav className="guest-sidebar-primary" aria-label="Navigasi guest">
        <button
          type="button"
          className="guest-new-chat"
          onClick={() => {
            onNewConversation();
            onMobileSidebarOpenChange(false);
          }}
        >
          <PlusIcon />
          <span>Chat baru</span>
        </button>
        <Link href="/search">
          <SearchIcon className="icon" />
          <span>Cari Regulasi</span>
        </Link>
        <Link href="/legal/disclaimer">
          <FileIcon className="icon" />
          <span>Legal &amp; Bantuan</span>
        </Link>
      </nav>
      <div className="guest-sidebar-spacer" />
      <div className="guest-sidebar-signin">
        <strong>Simpan percakapan Anda</strong>
        <p>Masuk agar riwayat dan jawaban tetap tersedia saat Anda kembali.</p>
        <button type="button" onClick={(event) => openAuthModal(event.currentTarget)}>
          Masuk
        </button>
      </div>
    </>
  );

  const sidebarContent = session ? authenticatedSidebarContent : guestSidebarContent;

  return (
    <div
      className={[
        "chatgpt-shell",
        "guest-shell",
        session ? "authenticated-shell" : "",
        sidebarExpanded ? "sidebar-expanded" : "sidebar-collapsed",
        sourceDrawerOpen ? "source-open" : "",
      ].join(" ")}
    >
      <aside className="chatgpt-sidebar desktop-sidebar">
        {sidebarContent}
        <nav className="collapsed-sidebar-rail" aria-label="Navigasi sidebar ringkas">
          <Link href="/" className="collapsed-sidebar-button" aria-label="KerjaPedia AI beranda">
            <ScaleIcon />
          </Link>
          <button
            type="button"
            className="collapsed-sidebar-button"
            aria-label="Percakapan baru"
            onClick={onNewConversation}
          >
            <EditIcon />
          </button>
          <button
            type="button"
            className="collapsed-sidebar-button"
            aria-label="Cari chat"
            onClick={(event) => openChatSearch(event.currentTarget)}
          >
            <SearchIcon />
          </button>
          <Link
            href="/legal/disclaimer"
            className="collapsed-sidebar-button"
            aria-label="Legal dan bantuan"
          >
            <FileIcon />
          </Link>
          <button
            type="button"
            className="collapsed-sidebar-button collapsed-sidebar-profile"
            aria-label={session ? "Buka profil pengguna" : "Masuk atau daftar"}
            onClick={(event) => {
              if (session) {
                onSidebarExpandedChange(true);
              } else {
                openAuthModal(event.currentTarget);
              }
            }}
          >
            <UserIcon />
          </button>
        </nav>
      </aside>
      <div className="chatgpt-stage">
        <header className="chatgpt-topbar">
          <button
            type="button"
            className="chatgpt-icon-button chatgpt-topbar-sidebar-toggle desktop-only"
            aria-label={sidebarExpanded ? "Tutup sidebar" : "Buka sidebar"}
            aria-expanded={sidebarExpanded}
            aria-hidden={sidebarExpanded}
            tabIndex={sidebarExpanded ? -1 : 0}
            onClick={() => onSidebarExpandedChange(!sidebarExpanded)}
          >
            <PanelIcon />
          </button>
          <button
            ref={mobileMenuRef}
            type="button"
            className="chatgpt-icon-button mobile-only"
            aria-label={session ? "Buka riwayat" : "Buka menu"}
            aria-expanded={mobileSidebarOpen}
            onClick={() => onMobileSidebarOpenChange(true)}
          >
            <MenuIcon />
          </button>
          <div className="chatgpt-mobile-brand mobile-only">
            <span>KP</span>
          </div>
          <h1>KerjaPedia AI</h1>
          {!session ? (
            <div className="guest-auth-actions">
              <button
                type="button"
                className="guest-login-button"
                onClick={(event) => openAuthModal(event.currentTarget, "login")}
              >
                Masuk
              </button>
              <button
                type="button"
                className="guest-signup-button"
                onClick={(event) => openAuthModal(event.currentTarget, "signup")}
              >
                Daftar gratis
              </button>
            </div>
          ) : null}
        </header>
        {session && profileMenuOpen ? (
          <div
            ref={profileMenuRef}
            className="profile-menu"
            role="menu"
            aria-label="Menu profil pengguna"
          >
            <div className="profile-menu-header">
              <span>{session.user.name.slice(0, 2).toUpperCase()}</span>
              <div>
                <strong>{session.user.name}</strong>
                <small>{session.user.roles.join(", ")}</small>
              </div>
            </div>
            <div className="profile-menu-section">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onSidebarExpandedChange(true);
                  setProfileMenuOpen(false);
                }}
              >
                <UserIcon />
                <span>Profil &amp; riwayat</span>
              </button>
              <Link href="/search" role="menuitem" onClick={() => setProfileMenuOpen(false)}>
                <SearchIcon />
                <span>Cari Regulasi</span>
              </Link>
              <Link href="/legal/privacy" role="menuitem" onClick={() => setProfileMenuOpen(false)}>
                <SettingsIcon />
                <span>Privasi</span>
              </Link>
              {session.user.roles.includes("admin") ? (
                <Link
                  href="/admin/settings"
                  role="menuitem"
                  onClick={() => setProfileMenuOpen(false)}
                >
                  <SettingsIcon />
                  <span>Pengaturan</span>
                </Link>
              ) : null}
            </div>
            <div className="profile-menu-section">
              <Link
                href="/legal/disclaimer"
                role="menuitem"
                onClick={() => setProfileMenuOpen(false)}
              >
                <FileIcon />
                <span>Bantuan</span>
              </Link>
              <button type="button" role="menuitem" onClick={handleLogout}>
                <LogoutIcon />
                <span>Keluar</span>
              </button>
            </div>
          </div>
        ) : null}
        <main className="chatgpt-main">{children}</main>
      </div>
      {sourceDrawerOpen && sourcePanel ? (
        <aside className="chatgpt-source-drawer" aria-label="Sumber dan kutipan">
          <header>
            <h2>Sumber</h2>
            <button
              ref={sourceCloseRef}
              type="button"
              className="chatgpt-icon-button"
              aria-label="Tutup sumber"
              onClick={onSourceDrawerClose}
            >
              <CloseIcon />
            </button>
          </header>
          {sourcePanel}
        </aside>
      ) : null}
      {mobileSidebarOpen ? (
        <div className="chatgpt-mobile-sidebar-layer">
          <button
            type="button"
            className="chatgpt-sidebar-backdrop"
            aria-label={session ? "Tutup riwayat" : "Tutup menu"}
            onClick={() => onMobileSidebarOpenChange(false)}
          />
          <aside
            ref={mobileSidebarRef}
            className="chatgpt-sidebar mobile-sidebar"
            role="dialog"
            aria-modal="true"
            aria-label={session ? "Riwayat percakapan" : "Menu KerjaPedia"}
            onKeyDown={keepMobileFocusInside}
          >
            {sidebarContent}
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
    </div>
  );
}
