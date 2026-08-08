"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState, useEffect, useSyncExternalStore, type ReactNode } from "react";

import {
  ChartIcon,
  ChatIcon,
  DatabaseIcon,
  FileIcon,
  GaugeIcon,
  LogoutIcon,
  PanelLeftIcon,
  PlayIcon,
  ScaleIcon,
  SettingIcon,
  UploadIcon,
  UserIcon,
} from "./icons";
import { useStoredSession } from "@/hooks/use-stored-session";
import { signOut } from "@/lib/api";

type AdminShellProps = { children: ReactNode };

const adminNavigation = [
  { href: "/admin/dashboard", label: "Dashboard", icon: ChartIcon },
  { href: "/documents", label: "Dokumen", icon: FileIcon },
  { href: "/admin/upload", label: "Upload PDF", icon: UploadIcon },
  { href: "/admin/ingestion", label: "Ingestion", icon: DatabaseIcon },
  { href: "/admin/feedback", label: "Feedback", icon: ChatIcon },
  { href: "/admin/retrieval", label: "Retrieval Playground", icon: PlayIcon },
  { href: "/admin/evaluation", label: "Evaluasi RAG", icon: GaugeIcon },
];

function useIsClient() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
}

export function AdminShell({ children }: AdminShellProps) {
  const isClient = useIsClient();
  const pathname = usePathname();
  const session = useStoredSession();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isClient) {
    return null;
  }

  if (!session || !session.user.roles.includes("admin")) {
    return (
      <div className="admin-access-page">
        <div className="admin-access-panel">
          <span className="admin-access-mark">
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

  const isActive = (href: string) =>
    href === "/documents" ? pathname === "/documents" : pathname.startsWith(href);

  async function handleLogout() {
    try {
      await signOut();
    } finally {
      window.location.assign("/login-admin");
    }
  }

  return (
    <div className={sidebarCollapsed ? "admin-shell collapsed" : "admin-shell"}>
      <aside className="admin-shell-sidebar" aria-label="Navigasi admin">
        <div className="admin-shell-sidebar-inner">
          <div className="admin-shell-sidebar-brand">
            <span className="admin-shell-sidebar-mark">
              <ScaleIcon />
            </span>
            <span className="admin-shell-sidebar-title">KerjaPedia AI</span>
            {!sidebarCollapsed && (
              <button
                type="button"
                className="admin-shell-collapse-btn"
                aria-label="Tutup sidebar"
                onClick={() => setSidebarCollapsed(true)}
              >
                <PanelLeftIcon className="icon" />
              </button>
            )}
          </div>
          <nav className="admin-shell-nav">
            {adminNavigation.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              return (
                <Link
                  href={item.href}
                  key={item.href}
                  className={active ? "admin-shell-nav-item active" : "admin-shell-nav-item"}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon className="icon" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>
      <div className="admin-shell-body">
        <header className="admin-shell-topbar">
          <div className="admin-shell-topbar-left">
            {sidebarCollapsed && (
              <button
                type="button"
                className="admin-shell-collapse-btn"
                aria-label="Buka sidebar"
                onClick={() => setSidebarCollapsed(false)}
              >
                <PanelLeftIcon className="icon" />
              </button>
            )}
            <span className="admin-shell-topbar-title">Dashboard</span>
          </div>
          <div className="admin-shell-topbar-right">
            <div className="admin-shell-topbar-user" ref={dropdownRef}>
              <button
                type="button"
                className="admin-shell-user-btn"
                onClick={() => setDropdownOpen(!dropdownOpen)}
              >
                <UserIcon className="icon" />
                <span>{session.user.name}</span>
              </button>
              {dropdownOpen && (
                <div className="admin-shell-dropdown">
                  <Link
                    href="/admin/settings"
                    className="admin-shell-dropdown-item"
                    onClick={() => setDropdownOpen(false)}
                  >
                    <SettingIcon className="icon" />
                    <span>Pengaturan</span>
                  </Link>
                  <button
                    type="button"
                    className="admin-shell-dropdown-item"
                    onClick={handleLogout}
                  >
                    <LogoutIcon className="icon" />
                    <span>Logout</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="admin-shell-main">{children}</main>
      </div>
    </div>
  );
}
