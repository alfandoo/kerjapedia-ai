"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { MessageSquare, Pencil, MoreHorizontal, Trash2 } from "lucide-react";
import type { ConversationSummary } from "@/lib/types";

type ConversationHistoryProps = {
  conversations: ConversationSummary[];
  activeConversationId?: string | null;
  loading?: boolean;
  onConversationSelect?: (conversationId: string) => void;
  onNewConversation?: () => void;
  onConversationRename?: (conversationId: string, title: string) => Promise<void>;
  onConversationDelete?: (conversationId: string) => Promise<void>;
  historyEnabled?: boolean;
  showNewConversation?: boolean;
  emptyMessage?: string;
};

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ConversationHistory({
  conversations,
  activeConversationId,
  loading = false,
  onConversationSelect,
  onNewConversation,
  onConversationRename,
  onConversationDelete,
  historyEnabled = true,
  showNewConversation = true,
  emptyMessage = "Belum ada percakapan. Ajukan pertanyaan pertama Anda.",
}: ConversationHistoryProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function closeMenu(event: PointerEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpenMenuId(null);
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenMenuId(null);
        setEditingId(null);
      }
    }
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  async function saveTitle(conversationId: string) {
    const title = draftTitle.trim();
    if (!title || !onConversationRename) return;
    setPendingId(conversationId);
    try {
      await onConversationRename(conversationId, title);
      setEditingId(null);
      setOpenMenuId(null);
    } catch {
      return;
    } finally {
      setPendingId(null);
    }
  }

  async function removeConversation(item: ConversationSummary) {
    if (!onConversationDelete) return;
    const confirmed = window.confirm(
      `Hapus percakapan "${item.title}"? Tindakan ini tidak dapat dibatalkan.`
    );
    if (!confirmed) return;
    setPendingId(item.conversation_id);
    try {
      await onConversationDelete(item.conversation_id);
      setOpenMenuId(null);
    } catch {
      return;
    } finally {
      setPendingId(null);
    }
  }

  return (
    <aside
      className="flex flex-col border-r border-[#dce4df] bg-white p-[32px_22px_20px_32px] max-[760px]:hidden"
      aria-label="Riwayat percakapan"
    >
      <h2 className="mb-5 font-display text-lg font-semibold text-tinta">Percakapan</h2>
      {showNewConversation ? (
        <button
          className="flex min-h-11 items-center gap-2.5 rounded-lg border border-[#bfd0c6] bg-white px-3.5 text-[13px] font-semibold text-javanese transition hover:border-javanese hover:bg-[#f3f8f5]"
          type="button"
          onClick={onNewConversation}
        >
          <span aria-hidden="true" className="text-xl font-normal">
            +
          </span>
          Percakapan baru
        </button>
      ) : null}
      <div className="mt-[22px] min-h-0 flex-1 overflow-y-auto" aria-busy={historyEnabled && loading}>
        {loading ? (
          <p
            className={`px-2.5 py-1 text-xs leading-relaxed text-muted-text ${
              historyEnabled ? "" : "hidden"
            }`}
          >
            Memuat riwayat…
          </p>
        ) : null}
        {!loading && conversations.length === 0 ? (
          <p
            className={`px-2.5 py-1 text-xs leading-relaxed text-muted-text ${
              historyEnabled ? "" : "hidden"
            }`}
          >
            {emptyMessage}
          </p>
        ) : null}
        {conversations.map((item) => (
          <div
            key={item.conversation_id}
            className={`group relative grid grid-cols-[minmax(0,1fr)_34px] items-center border-b border-[#edf1ee] transition ${
              item.conversation_id === activeConversationId ? "bg-[#f5f8f6]" : ""
            } ${historyEnabled ? "" : "hidden"}`}
          >
            {editingId === item.conversation_id ? (
              <form
                className="col-span-2 p-[9px]"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveTitle(item.conversation_id);
                }}
              >
                <label
                  htmlFor={`conversation-title-${item.conversation_id}`}
                  className="mb-1 block text-[10px] font-semibold text-muted-text"
                >
                  Ubah judul
                </label>
                <input
                  id={`conversation-title-${item.conversation_id}`}
                  value={draftTitle}
                  maxLength={80}
                  autoFocus
                  onChange={(event) => setDraftTitle(event.target.value)}
                  className="h-[34px] w-full rounded-md border border-[#9fb5a9] bg-white px-[9px] text-xs text-tinta outline-none transition focus:border-javanese focus:ring-2 focus:ring-[rgba(23,79,58,0.1)]"
                />
                <div className="mt-[7px] flex justify-end gap-1.5">
                  <button
                    type="button"
                    className="min-h-[30px] rounded-md border border-[#bdccc3] bg-white px-[9px] text-[11px] text-tinta transition hover:border-[#9fb5a9]"
                    onClick={() => setEditingId(null)}
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    disabled={!draftTitle.trim() || pendingId === item.conversation_id}
                    className="min-h-[30px] rounded-md border border-javanese bg-javanese px-[9px] text-[11px] text-white transition hover:bg-forest disabled:opacity-50"
                  >
                    Simpan
                  </button>
                </div>
              </form>
            ) : (
              <>
                <button
                  type="button"
                  className="grid w-full grid-cols-[17px_minmax(0,1fr)] gap-2.5 bg-transparent p-[12px_9px] text-left text-tinta"
                  aria-current={item.conversation_id === activeConversationId ? "true" : undefined}
                  onClick={() => onConversationSelect?.(item.conversation_id)}
                >
                  <MessageSquare className="mt-0.5 size-4 text-[#78827c]" />
                  <span className="min-w-0">
                    <strong className="block truncate text-xs font-semibold">
                      {item.title}
                    </strong>
                    <small className="mt-1.5 block text-[10px] text-muted-text">
                      {formatHistoryTime(item.updated_at)}
                    </small>
                  </span>
                </button>
                <div
                  className="relative grid place-items-center pr-0.5"
                  ref={openMenuId === item.conversation_id ? menuRef : undefined}
                >
                  <button
                    type="button"
                    className={`grid size-8 place-items-center rounded-[7px] text-[#66716b] transition hover:bg-[#dce7e1] hover:text-tinta ${
                      item.conversation_id === activeConversationId
                        ? "opacity-100"
                        : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 aria-expanded:opacity-100"
                    }`}
                    aria-label={`Tindakan untuk ${item.title}`}
                    aria-haspopup="menu"
                    aria-expanded={openMenuId === item.conversation_id}
                    onClick={() =>
                      setOpenMenuId((current) =>
                        current === item.conversation_id ? null : item.conversation_id
                      )
                    }
                  >
                    <MoreHorizontal className="size-[17px]" />
                  </button>
                  {openMenuId === item.conversation_id ? (
                    <div
                      className="absolute right-0 top-[34px] z-30 w-[138px] rounded-[9px] border border-[#ccd8d1] bg-white p-[5px] shadow-[0_10px_28px_rgba(20,43,31,0.14)]"
                      role="menu"
                    >
                      <button
                        type="button"
                        role="menuitem"
                        className="flex min-h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-xs text-tinta transition hover:bg-[#edf3ef]"
                        onClick={() => {
                          setDraftTitle(item.title);
                          setEditingId(item.conversation_id);
                        }}
                      >
                        <Pencil className="size-4 shrink-0" />
                        <span className="flex-1">Ubah judul</span>
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="flex min-h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-xs text-[#a33c31] transition hover:bg-[#fff1ef]"
                        disabled={pendingId === item.conversation_id}
                        onClick={() => void removeConversation(item)}
                      >
                        <Trash2 className="size-4 shrink-0" />
                        <span className="flex-1">Hapus chat</span>
                      </button>
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
