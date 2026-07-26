"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ChatIcon, EditIcon, MoreIcon, TrashIcon } from "./icons";
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
      `Hapus percakapan “${item.title}”? Tindakan ini tidak dapat dibatalkan.`
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
    <aside className="editorial-history" aria-label="Riwayat percakapan">
      <h2>Percakapan</h2>
      {showNewConversation ? (
        <button className="editorial-new-chat" type="button" onClick={onNewConversation}>
          <span aria-hidden="true">+</span>
          Percakapan baru
        </button>
      ) : null}
      <div
        className={`editorial-history-list${historyEnabled ? "" : " guest-mode"}`}
        aria-busy={historyEnabled && loading}
      >
        {!historyEnabled ? (
          <div className="editorial-guest-history">
            <strong>Riwayat tamu tidak disimpan</strong>
            <p>Masuk agar percakapan tetap tersedia saat Anda kembali.</p>
            <Link href="/login">Masuk untuk menyimpan</Link>
          </div>
        ) : null}
        {loading ? <p className="editorial-history-empty">Memuat riwayat…</p> : null}
        {!loading && conversations.length === 0 ? (
          <p className="editorial-history-empty">{emptyMessage}</p>
        ) : null}
        {conversations.map((item) => (
          <div
            key={item.conversation_id}
            className={
              item.conversation_id === activeConversationId
                ? "editorial-history-row active"
                : "editorial-history-row"
            }
          >
            {editingId === item.conversation_id ? (
              <form
                className="editorial-history-rename"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveTitle(item.conversation_id);
                }}
              >
                <label htmlFor={`conversation-title-${item.conversation_id}`}>Ubah judul</label>
                <input
                  id={`conversation-title-${item.conversation_id}`}
                  value={draftTitle}
                  maxLength={80}
                  autoFocus
                  onChange={(event) => setDraftTitle(event.target.value)}
                />
                <div>
                  <button type="button" onClick={() => setEditingId(null)}>
                    Batal
                  </button>
                  <button
                    type="submit"
                    disabled={!draftTitle.trim() || pendingId === item.conversation_id}
                  >
                    Simpan
                  </button>
                </div>
              </form>
            ) : (
              <>
                <button
                  type="button"
                  className="editorial-history-item"
                  aria-current={item.conversation_id === activeConversationId ? "true" : undefined}
                  onClick={() => onConversationSelect?.(item.conversation_id)}
                >
                  <ChatIcon className="icon" />
                  <span>
                    <strong>{item.title}</strong>
                    <small>{formatHistoryTime(item.updated_at)}</small>
                  </span>
                </button>
                <div
                  className="editorial-history-actions"
                  ref={openMenuId === item.conversation_id ? menuRef : undefined}
                >
                  <button
                    type="button"
                    className="editorial-history-more"
                    aria-label={`Tindakan untuk ${item.title}`}
                    aria-haspopup="menu"
                    aria-expanded={openMenuId === item.conversation_id}
                    onClick={() =>
                      setOpenMenuId((current) =>
                        current === item.conversation_id ? null : item.conversation_id
                      )
                    }
                  >
                    <MoreIcon className="icon" />
                  </button>
                  {openMenuId === item.conversation_id ? (
                    <div className="editorial-history-menu" role="menu">
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setDraftTitle(item.title);
                          setEditingId(item.conversation_id);
                        }}
                      >
                        <EditIcon className="icon" />
                        <span>Ubah judul</span>
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="danger"
                        disabled={pendingId === item.conversation_id}
                        onClick={() => void removeConversation(item)}
                      >
                        <TrashIcon className="icon" />
                        <span>Hapus chat</span>
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
