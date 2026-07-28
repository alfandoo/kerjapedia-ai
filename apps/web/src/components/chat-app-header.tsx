"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useStoredSession } from "@/hooks/use-stored-session";

const navigation = [
  { href: "/", label: "Chat" },
  { href: "/search", label: "Cari Regulasi" },
  { href: "/admin", label: "Admin" },
  { href: "/legal/disclaimer", label: "Legal" },
];

export function ChatAppHeader() {
  const pathname = usePathname();
  const session = useStoredSession();

  return (
    <header className="editorial-header">
      <Link href="/chat" className="editorial-brand" aria-label="KerjaPedia AI beranda">
        <span className="editorial-brand-mark">KP</span>
        <span>KerjaPedia AI</span>
      </Link>
      <nav className="editorial-nav" aria-label="Navigasi utama">
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
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
      <Link href="/login" className="editorial-session">
        <span className="editorial-avatar">
          {session ? session.user.name.slice(0, 2).toUpperCase() : "TM"}
        </span>
        <span>
          <strong>{session ? session.user.name : "Tamu"}</strong>
          <small>{session ? session.user.roles.join(", ") : "Belum masuk"}</small>
        </span>
      </Link>
    </header>
  );
}
