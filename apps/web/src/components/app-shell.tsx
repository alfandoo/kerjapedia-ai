"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ChatIcon, DatabaseIcon, FileIcon, ScaleIcon, SearchIcon } from "./icons";
import { useStoredSession } from "@/hooks/use-stored-session";
import { sampleHistory } from "@/lib/sample-data";

type AppShellProps = {
  children: ReactNode;
  rightPanel?: ReactNode;
};

const navigation = [
  { href: "/", label: "Chat", icon: ChatIcon },
  { href: "/search", label: "Cari Regulasi", icon: SearchIcon },
  { href: "/admin", label: "Admin", icon: DatabaseIcon },
  { href: "/legal/disclaimer", label: "Legal", icon: FileIcon },
];

export function AppShell({ children, rightPanel }: AppShellProps) {
  const pathname = usePathname();
  const session = useStoredSession();

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link href="/" className="brand" aria-label="KerjaPedia AI beranda">
          <span className="brand-mark">
            <ScaleIcon className="icon" />
          </span>
          <span>KerjaPedia AI</span>
        </Link>
        <nav className="topnav" aria-label="Navigasi utama">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-item active" : "nav-item"}
              >
                <Icon className="icon" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <Link href="/login" className="session-chip">
          <span className="avatar">
            {session ? session.user.name.slice(0, 2).toUpperCase() : "AR"}
          </span>
          <span>
            <strong>{session ? session.user.name : "Andi Rahman"}</strong>
            <small>{session ? session.user.roles.join(", ") : "Guest"}</small>
          </span>
        </Link>
      </header>
      <div className="workspace">
        <aside className="history-rail" aria-label="Riwayat percakapan">
          <div className="rail-header">
            <h2>Riwayat</h2>
            <button className="secondary-button" type="button">
              + Percakapan baru
            </button>
          </div>
          <div className="history-list">
            {sampleHistory.map((item) => (
              <button
                key={item.title}
                type="button"
                className={item.active ? "history-item active" : "history-item"}
              >
                <ChatIcon className="icon" />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.time}</small>
                </span>
              </button>
            ))}
          </div>
          <Link href="/search" className="rail-link">
            <SearchIcon className="icon" />
            Lihat semua regulasi
          </Link>
        </aside>
        <main className="main-pane">{children}</main>
        <aside className="source-rail" aria-label="Sumber dan kutipan">
          {rightPanel}
        </aside>
      </div>
    </div>
  );
}
