"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useStoredSession } from "@/hooks/use-stored-session";

export function ChatAppHeader() {
  const pathname = usePathname();
  const session = useStoredSession();

  const navigation = [
    { href: "/chat", label: "Chat" },
    { href: "/search", label: "Cari Regulasi" },
    ...(session?.user.roles.includes("admin")
      ? [{ href: "/admin/dashboard", label: "Admin" }]
      : []),
    { href: "/legal/disclaimer", label: "Legal" },
  ];

  return (
    <header className="editorial-header">
      <Link href="/chat" className="editorial-brand" aria-label="KerjaPedia AI beranda">
        <span className="editorial-brand-mark">KP</span>
        <span>KerjaPedia AI</span>
      </Link>
      <nav className="editorial-nav" aria-label="Navigasi utama">
        {navigation.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={active ? "editorial-nav-item active" : "editorial-nav-item"}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      {session ? (
        <Link
          href={session.user.roles.includes("admin") ? "/admin/dashboard" : "/chat"}
          className="editorial-session"
        >
          <span className="editorial-avatar">{session.user.name.slice(0, 2).toUpperCase()}</span>
          <span>
            <strong>{session.user.name}</strong>
            <small>{session.user.roles.join(", ")}</small>
          </span>
        </Link>
      ) : (
        <Link href="/register" className="editorial-session">
          <span className="editorial-avatar">TM</span>
          <span>
            <strong>Tamu</strong>
            <small>Masuk / Daftar</small>
          </span>
        </Link>
      )}
    </header>
  );
}
