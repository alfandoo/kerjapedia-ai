"use client";

import Link from "next/link";
import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";

import { DatabaseIcon, FileIcon, SearchIcon } from "./icons";
import { ConversationHistory } from "./conversation-history";
import { useStoredSession } from "@/hooks/use-stored-session";
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
        <Link href="/" className="chatgpt-brand" aria-label="KerjaPedia AI beranda">
          <span>KP</span>
          <strong>KerjaPedia AI</strong>
        </Link>
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
      <ConversationHistory
        conversations={conversations}
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
      />
      <nav className="chatgpt-sidebar-nav" aria-label="Navigasi produk">
        <Link href="/search">
          <SearchIcon className="icon" />
          <span>Cari Regulasi</span>
        </Link>
        <Link href="/admin">
          <DatabaseIcon className="icon" />
          <span>Admin</span>
        </Link>
        <Link href="/legal/disclaimer">
          <FileIcon className="icon" />
          <span>Legal</span>
        </Link>
      </nav>
      <Link href="/login" className="chatgpt-account">
        <span className="chatgpt-account-avatar">
          {session ? session.user.name.slice(0, 2).toUpperCase() : "TM"}
        </span>
        <span>
          <strong>{session ? session.user.name : "Tamu"}</strong>
          <small>{session ? session.user.roles.join(", ") : "Belum masuk"}</small>
        </span>
      </Link>
    </>
  );

  const guestSidebarContent = (
    <>
      <div className="chatgpt-sidebar-heading">
        <Link href="/" className="chatgpt-brand" aria-label="KerjaPedia AI beranda">
          <span>KP</span>
          <strong>KerjaPedia AI</strong>
        </Link>
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
        <Link href="/login">Masuk</Link>
      </div>
    </>
  );

  const sidebarContent = session ? authenticatedSidebarContent : guestSidebarContent;

  return (
    <div
      className={[
        "chatgpt-shell",
        session ? "authenticated-shell" : "guest-shell",
        sidebarExpanded ? "sidebar-expanded" : "sidebar-collapsed",
        sourceDrawerOpen ? "source-open" : "",
      ].join(" ")}
    >
      <aside className="chatgpt-sidebar desktop-sidebar">{sidebarContent}</aside>
      <div className="chatgpt-stage">
        <header className="chatgpt-topbar">
          <button
            type="button"
            className="chatgpt-icon-button desktop-only"
            aria-label={sidebarExpanded ? "Tutup sidebar" : "Buka sidebar"}
            aria-expanded={sidebarExpanded}
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
          <h1>{session ? "Asisten Regulasi Ketenagakerjaan" : "KerjaPedia AI"}</h1>
          {session ? (
            <button
              type="button"
              className="chatgpt-icon-button chatgpt-topbar-new"
              aria-label="Percakapan baru"
              onClick={onNewConversation}
            >
              <PlusIcon />
            </button>
          ) : (
            <div className="guest-auth-actions">
              <Link href="/login" className="guest-login-button">
                Masuk
              </Link>
              <Link href="/login?mode=signup" className="guest-signup-button">
                Daftar gratis
              </Link>
            </div>
          )}
        </header>
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
    </div>
  );
}
