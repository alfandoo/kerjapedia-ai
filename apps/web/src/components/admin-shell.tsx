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
    <div className="admin-shell">
      <header className="admin-topbar">
        <Link href="/chat" className="brand" aria-label="KerjaPedia AI beranda">
          <span className="brand-mark">
            <ScaleIcon className="icon" />
          </span>
          <span>KerjaPedia AI</span>
        </Link>
        <strong className="admin-product-title">Admin Knowledge Base</strong>
        <Link href="/chat" className="admin-back-link">
          Kembali ke Chat
        </Link>
        <div className="session-chip">
          <span className="avatar">{session.user.name.slice(0, 2).toUpperCase()}</span>
          <span>
            <strong>{session.user.name}</strong>
            <small>Administrator</small>
          </span>
        </div>
      </header>
      <div className="admin-layout">
        <aside className="admin-sidebar" aria-label="Navigasi admin">
          <nav>
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
                  className={active ? "admin-nav-item active" : "admin-nav-item"}
                >
                  <Icon className="icon" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <Link href="/admin/settings" className="admin-nav-item admin-settings-link">
            <SettingsIcon className="icon" />
            Pengaturan
          </Link>
          <button
            type="button"
            className="admin-nav-item admin-logout-button"
            onClick={handleLogout}
          >
            <LogoutIcon className="icon" />
            Keluar
          </button>
        </aside>
        <main className="admin-main">{children}</main>
      </div>
    </div>
  );
}
