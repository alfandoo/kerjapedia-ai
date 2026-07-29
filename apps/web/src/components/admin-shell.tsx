"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import {
  ChartIcon,
  ChatIcon,
  DatabaseIcon,
  FileIcon,
  LogoutIcon,
  PlayIcon,
  ScaleIcon,
  SettingsIcon,
  UploadIcon,
} from "./icons";
import { SESSION_STORAGE_KEY } from "@/lib/api";
import { useStoredSession } from "@/hooks/use-stored-session";

type AdminShellProps = { children: ReactNode };

const adminNavigation = [
  { href: "/admin/dashboard", label: "Dashboard", icon: ChartIcon },
  { href: "/documents", label: "Dokumen", icon: FileIcon },
  { href: "/admin/upload", label: "Upload PDF", icon: UploadIcon },
  { href: "/admin/ingestion", label: "Ingestion", icon: DatabaseIcon },
  { href: "/admin/feedback", label: "Feedback", icon: ChatIcon },
  { href: "/admin/retrieval", label: "Retrieval Playground", icon: PlayIcon },
];

export function AdminShell({ children }: AdminShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useStoredSession();

  function handleLogout() {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    window.dispatchEvent(new Event("kerjapedia-session-change"));
    router.push("/");
  }

  if (!session || !session.user.roles.includes("admin")) {
    return (
      <div className="admin-access-page">
        <div className="admin-access-panel">
          <span className="brand-mark">
            <ScaleIcon className="icon" />
          </span>
          <h1>Akses admin diperlukan</h1>
          <p>Masuk dengan akun yang memiliki role admin untuk mengelola knowledge base.</p>
          <Link href="/login-admin" className="admin-primary-button">
            Login sebagai admin
          </Link>
          <Link href="/chat" className="admin-text-link">
            Kembali ke Chat
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="editorial-shell admin-editorial">
      <header className="editorial-header">
        <Link href="/chat" className="editorial-brand" aria-label="KerjaPedia AI beranda">
          <span className="editorial-brand-mark">
            <ScaleIcon style={{ width: 18, height: 18, strokeWidth: 2.2 }} />
          </span>
          <span>KerjaPedia AI</span>
        </Link>
        <nav className="editorial-nav" aria-label="Navigasi admin">
          <span className="editorial-nav-item active">Admin Knowledge Base</span>
        </nav>
        <div className="editorial-session">
          <span className="editorial-avatar">{session.user.name.slice(0, 2).toUpperCase()}</span>
          <span>
            <strong>{session.user.name}</strong>
            <small>Administrator</small>
          </span>
        </div>
      </header>
      <div className="editorial-workspace">
        <aside className="admin-editorial-sidebar" aria-label="Navigasi admin">
          <nav className="admin-editorial-nav">
            {adminNavigation.map((item) => {
              const Icon = item.icon;
              const active =
                item.href === "/documents"
                  ? pathname === "/documents"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  href={item.href}
                  key={item.href}
                  className={
                    active ? "admin-editorial-nav-item active" : "admin-editorial-nav-item"
                  }
                >
                  <Icon className="icon" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="admin-editorial-sidebar-footer">
            <Link href="/admin/settings" className="admin-editorial-nav-item">
              <SettingsIcon className="icon" />
              <span>Pengaturan</span>
            </Link>
            <button
              type="button"
              className="admin-editorial-nav-item admin-editorial-logout"
              onClick={handleLogout}
            >
              <LogoutIcon className="icon" />
              <span>Keluar</span>
            </button>
          </div>
        </aside>
        <main className="editorial-main">{children}</main>
      </div>
    </div>
  );
}
