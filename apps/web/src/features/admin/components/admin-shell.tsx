"use client";

import { readPreference, writePreference } from "@/lib/preference-cookie";

import Link from "next/link";
import { toast } from "sonner";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  Activity,
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
import { useStoredSession, useSessionReady } from "@/features/auth";
import { signOut } from "@/features/admin/api";
import { cn } from "@/lib/utils";
import sidebarStyles from "./admin-sidebar.module.css";

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
      { href: "/admin/observability", label: "Observability", icon: Activity },
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
  const router = useRouter();
  const session = useStoredSession();
  const sessionReady = useSessionReady();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => typeof window !== "undefined" && readPreference("kp-admin-sidebar") === "collapsed"
  );
  const dropdownRef = useRef<HTMLDivElement>(null);
  const asideRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const wasMobileOpenRef = useRef(false);

  function toggleCollapsed(next: boolean) {
    setSidebarCollapsed(next);
    writePreference("kp-admin-sidebar", next ? "collapsed" : "expanded");
  }

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  useEffect(() => {
    if (mobileOpen) {
      mobileCloseRef.current?.focus();
    } else if (wasMobileOpenRef.current) {
      menuButtonRef.current?.focus();
    }
    wasMobileOpenRef.current = mobileOpen;
  }, [mobileOpen]);

  function keepMobileFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab" || !mobileOpen) return;
    const focusable = asideRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
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

  const shouldRedirectToLogin =
    isClient && sessionReady && (!session || !session.user.roles.includes("admin"));

  useEffect(() => {
    if (shouldRedirectToLogin) {
      router.replace("/login-admin");
    }
  }, [router, shouldRedirectToLogin]);

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

  if (!isClient || !sessionReady || !session || shouldRedirectToLogin) {
    return null;
  }

  const isActive = (href: string) =>
    href === "/documents"
      ? pathname === "/documents"
      : pathname === href || pathname.startsWith(`${href}/`);
  const currentSection =
    [...allNavItems].reverse().find((item) => isActive(item.href))?.label ?? "Admin";

  async function handleLogout() {
    try {
      await signOut();
      // Full page redirect after logout clears all client state intentionally.
      window.location.assign("/login-admin"); // eslint-disable-line @next/next/no-location-assign-relative-destination
    } catch (error) {
      toast.error((error as Error).message);
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
        id="admin-sidebar"
        ref={asideRef}
        aria-label="Navigasi admin"
        onKeyDown={keepMobileFocusInside}
        className={cn(
          sidebarStyles.sidebar,
          "fixed inset-y-0 left-0 z-50 flex w-[264px] shrink-0 flex-col transition-transform duration-200 motion-reduce:transition-none lg:h-[100dvh] lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          sidebarCollapsed ? "lg:w-[76px]" : "lg:w-[248px]"
        )}
      >
        <div className="flex h-16 shrink-0 items-center gap-2 px-4">
          <span className={sidebarStyles.brandIcon}>
            <ScaleIcon className="size-5" />
          </span>
          <div className={cn("min-w-0 leading-tight", sidebarCollapsed ? "lg:hidden" : "flex-1")}>
            <p className="truncate font-display text-base font-semibold text-white">
              KerjaPedia AI
            </p>
            <p className={sidebarStyles.brandCaption}>Konsol admin</p>
          </div>
          <button
            type="button"
            ref={mobileCloseRef}
            className={`${sidebarStyles.toggle} ml-auto flex lg:hidden`}
            aria-label="Tutup menu"
            onClick={() => setMobileOpen(false)}
          >
            <ChevronLeft className="size-5" />
          </button>
          <button
            type="button"
            className={cn(
              sidebarStyles.toggle,
              "ml-auto hidden lg:flex",
              sidebarCollapsed && "lg:hidden"
            )}
            aria-label="Ciutkan sidebar"
            aria-controls="admin-sidebar"
            aria-expanded={!sidebarCollapsed}
            onClick={() => toggleCollapsed(true)}
          >
            <PanelLeftClose className="size-4" />
          </button>
        </div>

        <nav
          className={cn(
            `${sidebarStyles.navigation} flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 pt-4 pb-6`,
            sidebarCollapsed && "lg:gap-3"
          )}
          aria-label="Menu admin"
        >
          {adminNavGroups.map((group) => (
            <div key={group.label} className="space-y-1">
              <p className={cn(sidebarStyles.groupLabel, sidebarCollapsed && "lg:hidden")}>
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
                      sidebarStyles.item,
                      sidebarCollapsed && "lg:justify-center lg:px-0",
                      active && sidebarStyles.active
                    )}
                  >
                    <Icon className="size-[19px] shrink-0" aria-hidden="true" />
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

      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col bg-arsip",
          sidebarCollapsed ? "lg:pl-[76px]" : "lg:pl-[248px]"
        )}
      >
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-3 border-b border-line bg-white px-4 lg:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              ref={menuButtonRef}
              className="-ml-1 flex size-11 items-center justify-center rounded-lg text-javanese transition hover:bg-surface-soft lg:hidden"
              aria-label="Buka menu navigasi"
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="size-5" />
            </button>
            {sidebarCollapsed && (
              <button
                type="button"
                className="hidden size-11 items-center justify-center rounded-lg text-javanese transition hover:bg-surface-soft lg:flex"
                aria-label="Buka sidebar"
                aria-controls="admin-sidebar"
                aria-expanded={!sidebarCollapsed}
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
