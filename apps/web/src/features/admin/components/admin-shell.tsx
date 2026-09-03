"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import {
  ChevronLeft,
  Database,
  FileUp,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  LogOut,
  type LucideIcon,
  Menu,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Settings,
  User,
} from "lucide-react";

import { ScaleIcon } from "@/components/icons";
import { useStoredSession } from "@/features/auth";
import { signOut } from "@/features/admin/api";
import { cn } from "@/lib/utils";

type AdminShellProps = { children: ReactNode };

const adminNavGroups: {
  label: string;
  items: { href: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    label: "Ikhtisar",
    items: [{ href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Pengelolaan",
    items: [
      { href: "/documents", label: "Dokumen", icon: ScrollText },
      { href: "/admin/upload", label: "Upload PDF", icon: FileUp },
      { href: "/admin/ingestion", label: "Ingestion", icon: Database },
    ],
  },
  {
    label: "Evaluasi",
    items: [
      { href: "/admin/feedback", label: "Feedback", icon: MessagesSquare },
      { href: "/admin/retrieval", label: "Retrieval Playground", icon: FlaskConical },
      { href: "/admin/evaluation", label: "Evaluasi RAG", icon: Gauge },
    ],
  },
];

const allNavItems = adminNavGroups.flatMap((group) => group.items);

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
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.localStorage.getItem("kp-admin-sidebar") === "collapsed"
  );
  const dropdownRef = useRef<HTMLDivElement>(null);

  function toggleCollapsed(next: boolean) {
    setSidebarCollapsed(next);
    window.localStorage.setItem("kp-admin-sidebar", next ? "collapsed" : "expanded");
  }

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setDropdownOpen(false);
      setMobileOpen(false);
    }
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeydown);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("keydown", handleKeydown);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  if (!isClient) {
    return null;
  }

  if (!session || !session.user.roles.includes("admin")) {
    return (
      <div className="admin-theme flex min-h-[100svh] items-center justify-center bg-arsip px-4">
        <div className="w-full max-w-md rounded-2xl border border-line bg-white p-10 text-center shadow-[0_16px_40px_rgba(27,67,50,0.08)]">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-javanese text-emas">
            <ScaleIcon className="size-7" />
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
  const currentSection =
    [...allNavItems].reverse().find((item) => isActive(item.href))?.label ?? "Admin";

  async function handleLogout() {
    try {
      await signOut();
    } finally {
      window.location.assign("/login-admin");
    }
  }

  return (
    <div className="admin-theme flex min-h-[100svh]">
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Tutup menu navigasi"
          className="fixed inset-0 z-40 bg-tinta/40 lg:hidden motion-reduce:transition-none"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <aside
        aria-label="Navigasi admin"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[264px] shrink-0 flex-col bg-javanese transition-transform duration-200 motion-reduce:transition-none lg:sticky lg:top-0 lg:h-[100svh] lg:self-start lg:bottom-auto lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          sidebarCollapsed ? "lg:w-[76px]" : "lg:w-[248px]"
        )}
      >
        <div className="flex h-16 shrink-0 items-center gap-2 border-b border-white/10 px-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-emas">
            <ScaleIcon className="size-5" />
          </span>
          <div className={cn("min-w-0 leading-tight", sidebarCollapsed ? "lg:hidden" : "flex-1")}>
            <p className="truncate font-display text-base font-semibold tracking-wide text-white">
              KerjaPedia AI
            </p>
            <p className="font-mono text-[10px] tracking-[0.22em] text-emas/90 uppercase">
              Konsol admin
            </p>
          </div>
          <button
            type="button"
            className="ml-auto flex size-8 shrink-0 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white lg:hidden"
            aria-label="Tutup menu"
            onClick={() => setMobileOpen(false)}
          >
            <ChevronLeft className="size-5" />
          </button>
          <button
            type="button"
            className={cn(
              "ml-auto hidden size-8 shrink-0 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white lg:flex",
              sidebarCollapsed && "lg:hidden"
            )}
            aria-label="Ciutkan sidebar"
            onClick={() => toggleCollapsed(true)}
          >
            <PanelLeftClose className="size-4" />
          </button>
        </div>

        <nav
          className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4"
          aria-label="Menu admin"
        >
          {adminNavGroups.map((group) => (
            <div key={group.label} className="space-y-1">
              <p
                className={cn(
                  "px-3 pb-1 font-mono text-[10px] font-semibold tracking-[0.2em] text-white/35 uppercase",
                  sidebarCollapsed && "lg:hidden"
                )}
              >
                {group.label}
              </p>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.href);
                return (
                  <Link
                    href={item.href}
                    key={item.href}
                    aria-current={active ? "page" : undefined}
                    title={sidebarCollapsed ? item.label : undefined}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emas",
                      sidebarCollapsed && "lg:justify-center lg:px-0",
                      active
                        ? "bg-white/10 font-semibold text-white"
                        : "text-white/60 hover:bg-white/[0.06] hover:text-white"
                    )}
                  >
                    {active ? (
                      <span
                        aria-hidden="true"
                        className="absolute inset-y-[9px] left-0 w-[3px] rounded-r-full bg-emas"
                      />
                    ) : null}
                    <Icon
                      className={cn(
                        "size-5 shrink-0 transition-colors",
                        active ? "text-emas" : "text-current"
                      )}
                    />
                    <span className={cn("truncate", sidebarCollapsed && "lg:hidden")}>
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col bg-arsip">
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-3 border-b border-line bg-white px-4 lg:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              className="-ml-1 flex size-9 items-center justify-center rounded-lg text-javanese transition hover:bg-surface-soft lg:hidden"
              aria-label="Buka menu navigasi"
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="size-5" />
            </button>
            {sidebarCollapsed && (
              <button
                type="button"
                className="hidden size-9 items-center justify-center rounded-lg text-javanese transition hover:bg-surface-soft lg:flex"
                aria-label="Buka sidebar"
                onClick={() => toggleCollapsed(false)}
              >
                <PanelLeftOpen className="size-4" />
              </button>
            )}
            <nav aria-label="Lokasi halaman" className="flex min-w-0 items-center gap-2 text-sm">
              <span className="hidden font-mono text-[11px] tracking-[0.18em] text-muted-text uppercase sm:inline">
                Admin
              </span>
              <span aria-hidden="true" className="hidden text-muted-text/50 sm:inline">
                /
              </span>
              <span className="truncate font-semibold text-tinta">{currentSection}</span>
            </nav>
          </div>
          <div className="relative shrink-0" ref={dropdownRef}>
            <button
              type="button"
              className="flex h-10 items-center gap-2.5 rounded-xl border border-line bg-white px-2.5 transition hover:border-javanese/30"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-expanded={dropdownOpen}
              aria-haspopup="menu"
            >
              <span className="flex size-7 items-center justify-center rounded-lg bg-javanese text-white">
                <User className="size-4" />
              </span>
              <span className="max-w-40 truncate text-sm font-medium text-tinta">
                {session.user.name}
              </span>
            </button>
            {dropdownOpen && (
              <div
                role="menu"
                className="absolute right-0 top-12 w-52 overflow-hidden rounded-xl border border-line bg-white shadow-[0_12px_32px_rgba(27,67,50,0.12)]"
              >
                <Link
                  href="/admin/settings"
                  role="menuitem"
                  className="flex h-11 items-center gap-2.5 px-4 text-sm text-tinta transition hover:bg-surface-soft"
                  onClick={() => setDropdownOpen(false)}
                >
                  <Settings className="size-4 text-muted-text" />
                  <span>Pengaturan</span>
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  className="flex h-11 w-full items-center gap-2.5 px-4 text-sm text-tinta transition hover:bg-surface-soft"
                  onClick={handleLogout}
                >
                  <LogOut className="size-4 text-muted-text" />
                  <span>Logout</span>
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
