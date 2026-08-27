"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useStoredSession } from "@/hooks/use-stored-session";
import { useSettings } from "./settings-provider";

export function ChatAppHeader() {
  const pathname = usePathname();
  const session = useStoredSession();
  const { t: translate } = useSettings();

  const navigation = [
    { href: "/chat", label: translate("chat.badge") },
    { href: "/search", label: translate("sidebar.searchRegulations") },
    ...(session?.user.roles.includes("admin")
      ? [{ href: "/admin/dashboard", label: "Admin" }]
      : []),
    { href: "/legal/disclaimer", label: translate("sidebar.legal") },
  ];

  return (
    <header className="grid h-[78px] grid-cols-[260px_minmax(0,1fr)_220px] items-center gap-6 border-b border-[#dce4df] bg-white px-8 max-[760px]:h-auto max-[760px]:grid-cols-[1fr_auto] max-[760px]:gap-x-4 max-[760px]:gap-y-2 max-[760px]:px-4 max-[760px]:pt-2.5">
      <Link
        href="/chat"
        className="flex w-fit items-center gap-[13px] font-display text-[21px] font-semibold leading-none tracking-[-0.02em] text-tinta transition hover:text-forest max-[760px]:text-lg"
        aria-label="KerjaPedia AI beranda"
      >
        <span className="grid size-[42px] place-items-center rounded-[9px] bg-javanese text-[13px] font-bold tracking-[0.06em] text-white max-[760px]:size-9">
          KP
        </span>
        <span>KerjaPedia AI</span>
      </Link>
      <nav
        className="flex h-full items-stretch justify-center gap-[34px] max-[760px]:col-span-2 max-[760px]:row-start-2 max-[760px]:h-11 max-[760px]:justify-start max-[760px]:gap-6 max-[760px]:overflow-x-auto"
        aria-label="Navigasi utama"
      >
        {navigation.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`relative grid min-h-11 place-items-center whitespace-nowrap text-sm font-medium text-[#5e6862] transition hover:text-javanese max-[760px]:flex-none max-[760px]:text-xs ${
                active
                  ? "text-javanese after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 after:bg-javanese"
                  : ""
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      {session ? (
        <Link
          href={session.user.roles.includes("admin") ? "/admin/dashboard" : "/chat"}
          className="flex min-h-11 items-center justify-self-end gap-2.5"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-full border border-[#cad7d0] bg-[#f5f8f6] text-xs font-bold text-javanese">
            {session.user.name.slice(0, 2).toUpperCase()}
          </span>
          <span className="max-[760px]:hidden">
            <strong className="block text-[13px] font-semibold text-tinta">
              {session.user.name}
            </strong>
            <small className="mt-0.5 block text-[11px] text-muted-text">
              {session.user.roles.join(", ")}
            </small>
          </span>
        </Link>
      ) : (
        <Link href="/register" className="flex min-h-11 items-center justify-self-end gap-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-full border border-[#cad7d0] bg-[#f5f8f6] text-xs font-bold text-javanese">
            TM
          </span>
          <span className="max-[760px]:hidden">
            <strong className="block text-[13px] font-semibold text-tinta">Tamu</strong>
            <small className="mt-0.5 block text-[11px] text-muted-text">Masuk / Daftar</small>
          </span>
        </Link>
      )}
    </header>
  );
}