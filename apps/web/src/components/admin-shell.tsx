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
      <div className="flex min-h-[100svh] items-center justify-center bg-arsip px-4">
        <div className="w-full max-w-md rounded-2xl border border-[#e8e6e1] bg-white p-10 text-center shadow-[0_16px_40px_rgba(27,67,50,0.08)]">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-javanese text-emas">
            <ScaleIcon className="icon size-7" />
          </span>
          <h1 className="mt-6 font-display text-2xl font-semibold text-javanese">
            Akses admin diperlukan
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted-text">
            Masuk dengan akun yang memiliki role admin untuk mengelola knowledge base.
          </p>
          <Link
            href="/login-admin"
            className="mt-7 inline-flex h-11 items-center justify-center rounded-xl bg-javanese px-6 text-sm font-semibold text-white transition hover:bg-forest"
          >
            Login sebagai admin
          </Link>
          <Link
            href="/chat"
            className="mt-4 block text-sm font-semibold text-forest transition hover:text-emas"
          >
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
    <div className="flex min-h-[100svh]">
      <aside
        className={`flex shrink-0 flex-col border-r border-[#e8ede9] bg-[#174f3a] transition-[width] duration-200 ${
          sidebarCollapsed ? "w-[72px]" : "w-[248px]"
        }`}
        aria-label="Navigasi admin"
      >
        <div className="flex flex-1 flex-col overflow-y-auto">
          <div className="flex h-16 items-center gap-3 border-b border-white/10 px-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-emas">
              <ScaleIcon />
            </span>
            {!sidebarCollapsed && (
              <>
                <span className="font-display text-base font-semibold tracking-wide text-white">
                  KerjaPedia AI
                </span>
                <button
                  type="button"
                  className="ml-auto flex size-8 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white"
                  aria-label="Tutup sidebar"
                  onClick={() => setSidebarCollapsed(true)}
                >
                  <PanelLeftIcon className="icon size-4" />
                </button>
              </>
            )}
          </div>
          <nav className="flex flex-1 flex-col gap-1 p-3">
            {adminNavigation.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              return (
                <Link
                  href={item.href}
                  key={item.href}
                  className={`flex h-11 items-center gap-3 rounded-lg px-3 text-sm transition ${
                    active
                      ? "bg-white/10 font-semibold text-white"
                      : "text-white/60 hover:bg-white/5 hover:text-white"
                  } ${sidebarCollapsed ? "justify-center px-0" : ""}`}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon className="icon size-5 shrink-0" />
                  {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col bg-arsip">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[#e8ede9] bg-white px-6">
          <div className="flex items-center gap-3">
            {sidebarCollapsed && (
              <button
                type="button"
                className="flex size-8 items-center justify-center rounded-lg text-javanese transition hover:bg-arsip"
                aria-label="Buka sidebar"
                onClick={() => setSidebarCollapsed(false)}
              >
                <PanelLeftIcon className="icon size-4" />
              </button>
            )}
            <span className="text-sm font-semibold text-tinta">Dashboard</span>
          </div>
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              className="flex h-10 items-center gap-2.5 rounded-xl border border-[#e8e6e1] bg-white px-3 transition hover:border-[#c9d5ce]"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-expanded={dropdownOpen}
            >
              <span className="flex size-7 items-center justify-center rounded-lg bg-javanese text-white">
                <UserIcon className="icon size-4" />
              </span>
              <span className="max-w-40 truncate text-sm font-medium text-tinta">
                {session.user.name}
              </span>
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 top-12 w-52 overflow-hidden rounded-xl border border-[#e8e6e1] bg-white shadow-[0_12px_32px_rgba(27,67,50,0.12)]">
                <Link
                  href="/admin/settings"
                  className="flex h-11 items-center gap-2.5 px-4 text-sm text-tinta transition hover:bg-arsip"
                  onClick={() => setDropdownOpen(false)}
                >
                  <SettingIcon className="icon size-4 text-muted-text" />
                  <span>Pengaturan</span>
                </Link>
                <button
                  type="button"
                  className="flex h-11 w-full items-center gap-2.5 px-4 text-sm text-tinta transition hover:bg-arsip"
                  onClick={handleLogout}
                >
                  <LogoutIcon className="icon size-4 text-muted-text" />
                  <span>Logout</span>
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 px-6 py-8 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
