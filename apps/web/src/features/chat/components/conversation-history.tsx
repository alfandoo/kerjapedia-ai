"use client";

import { useEffect, useRef, useState } from "react";

import { MessageSquare, MoreHorizontal, Pencil, Pin, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConversationSummary } from "@/features/chat/types";
import { useSettings } from "@/features/settings";
import { cn } from "@/lib/utils";

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
  mobileVisible?: boolean;
  embedded?: boolean;
  showTitle?: boolean;
  compact?: boolean;
  showPinnedIcon?: boolean;
  pinnedConversationIds?: string[];
  onTogglePinned?: (conversationId: string) => void;
};

type ConversationTitleButtonProps = {
  title: string;
  isActive: boolean;
  onSelect?: () => void;
};

function ConversationTitleButton({ title, isActive, onSelect }: ConversationTitleButtonProps) {
  const viewportRef = useRef<HTMLSpanElement>(null);
  const titleRef = useRef<HTMLElement>(null);

  function updateOverflowDistance() {
    const viewport = viewportRef.current;
    const titleElement = titleRef.current;
    if (!viewport || !titleElement) return;

    const overflow = Math.max(0, titleElement.scrollWidth - viewport.clientWidth);
    titleElement.dataset.overflow = overflow > 1 ? "true" : "false";
    titleElement.style.setProperty("--chat-title-offset", `-${overflow}px`);
  }

  return (
    <Button
      type="button"
      variant="ghost"
      className="h-8 min-w-0 justify-start rounded-none border-0 px-0.5 text-left shadow-none hover:bg-transparent"
      aria-current={isActive ? "page" : undefined}
      onPointerEnter={updateOverflowDistance}
      onFocus={updateOverflowDistance}
      onClick={onSelect}
    >
      <span
        ref={viewportRef}
        className="chat-history-title-viewport min-w-0 flex-1 overflow-hidden pr-4"
      >
        <strong
          ref={titleRef}
          data-overflow="false"
          className={cn(
            "chat-history-title block w-max whitespace-nowrap text-[13px] leading-5 transition-colors group-hover:text-sidebar-foreground",
            isActive
              ? "font-medium text-sidebar-foreground"
              : "font-normal text-sidebar-foreground/85"
          )}
        >
          {title}
        </strong>
      </span>
    </Button>
  );
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
  emptyMessage,
  mobileVisible = false,
  embedded = false,
  showTitle = true,
  compact = false,
  showPinnedIcon = false,
  pinnedConversationIds = [],
  onTogglePinned,
}: ConversationHistoryProps) {
  const { t: translate } = useSettings();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setEditingId(null);
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, []);

  async function saveTitle(conversationId: string) {
    const title = draftTitle.trim();
    if (!title || !onConversationRename) return;
    setPendingId(conversationId);
    try {
      await onConversationRename(conversationId, title);
      setEditingId(null);
    } catch {
      return;
    } finally {
      setPendingId(null);
    }
  }

  async function removeConversation(item: ConversationSummary) {
    if (!onConversationDelete) return;
    const confirmed = window.confirm(
      `${translate("sidebar.deleteConfirm")} “${item.title}”? ${translate("sidebar.deleteWarning")}`
    );
    if (!confirmed) return;
    setPendingId(item.conversation_id);
    try {
      await onConversationDelete(item.conversation_id);
    } catch {
      return;
    } finally {
      setPendingId(null);
    }
  }

  return (
    <section
      data-slot="conversation-history"
      className={cn(
        "min-w-0 border-r border-sidebar-border bg-sidebar px-2 text-sidebar-foreground",
        compact ? "pb-0 pt-0" : "pb-3 pt-2",
        embedded ? "block border-r-0" : "flex min-h-0 flex-col",
        !mobileVisible && "max-[760px]:hidden"
      )}
      aria-label={translate("sidebar.chatHistory")}
    >
      {showTitle ? (
        <div className="mb-1 px-0.5">
          <h2 className="truncate text-xs font-semibold text-sidebar-foreground">
            {translate("sidebar.chatHistory")}
          </h2>
        </div>
      ) : null}

      {showNewConversation ? (
        <Button
          className="mb-2 h-10 w-full justify-start"
          variant="outline"
          type="button"
          onClick={onNewConversation}
        >
          <Plus data-icon="inline-start" />
          {translate("sidebar.newChat")}
        </Button>
      ) : null}

      <div
        className={cn(
          "min-w-0",
          !embedded &&
            "history-scroll-region min-h-0 flex-1 overflow-y-auto overscroll-contain pr-0.5"
        )}
        aria-busy={historyEnabled && loading}
      >
        {loading && historyEnabled ? (
          <div className="flex flex-col gap-2 px-0.5 py-1" role="status">
            <span className="sr-only">{translate("sidebar.loadingHistory")}</span>
            <Skeleton className="h-3 w-16" />
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-9 w-full rounded-lg" />
            ))}
          </div>
        ) : null}

        {!loading && historyEnabled && conversations.length === 0 ? (
          <div className="flex min-h-36 flex-col items-center justify-center gap-2 px-5 text-center">
            <span className="grid size-8 place-items-center rounded-full bg-sidebar-accent text-muted-foreground">
              <MessageSquare className="size-4" aria-hidden="true" />
            </span>
            <p className="text-[11px] leading-5 text-muted-foreground">
              {emptyMessage || translate("sidebar.emptyHistory")}
            </p>
          </div>
        ) : null}

        {!loading && historyEnabled ? (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((item) => {
              const isActive = item.conversation_id === activeConversationId;
              const isEditing = editingId === item.conversation_id;
              const isPinned = pinnedConversationIds.includes(item.conversation_id);

              return (
                <li
                  key={item.conversation_id}
                  className="chat-history-row group relative rounded-lg transition-colors hover:bg-sidebar-accent focus-within:bg-sidebar-accent [content-visibility:auto] [contain-intrinsic-size:auto_32px]"
                >
                  {isEditing ? (
                    <form
                      className="flex flex-col gap-2 rounded-lg bg-sidebar-accent p-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void saveTitle(item.conversation_id);
                      }}
                    >
                      <Label
                        htmlFor={`conversation-title-${item.conversation_id}`}
                        className="text-[10px] text-muted-foreground"
                      >
                        {translate("sidebar.renameTitle")}
                      </Label>
                      <Input
                        id={`conversation-title-${item.conversation_id}`}
                        value={draftTitle}
                        maxLength={80}
                        autoFocus
                        onChange={(event) => setDraftTitle(event.target.value)}
                        className="h-8 bg-background text-xs"
                      />
                      <div className="flex justify-end gap-1.5">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingId(null)}
                        >
                          {translate("sidebar.cancel")}
                        </Button>
                        <Button
                          type="submit"
                          size="sm"
                          disabled={!draftTitle.trim() || pendingId === item.conversation_id}
                        >
                          {translate("sidebar.save")}
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div
                      className={`grid items-center ${
                        showPinnedIcon
                          ? "grid-cols-[20px_minmax(0,1fr)_0_0] group-hover:grid-cols-[20px_minmax(0,1fr)_32px_32px] group-focus-within:grid-cols-[20px_minmax(0,1fr)_32px_32px] max-[760px]:grid-cols-[20px_minmax(0,1fr)_32px_32px]"
                          : "grid-cols-[minmax(0,1fr)_0_0] group-hover:grid-cols-[minmax(0,1fr)_32px_32px] group-focus-within:grid-cols-[minmax(0,1fr)_32px_32px] max-[760px]:grid-cols-[minmax(0,1fr)_32px_32px]"
                      }`}
                    >
                      {showPinnedIcon ? (
                        <Pin className="size-3.5 text-[#d9f2df]" aria-hidden="true" />
                      ) : null}
                      <ConversationTitleButton
                        title={item.title}
                        isActive={isActive}
                        onSelect={() => onConversationSelect?.(item.conversation_id)}
                      />

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="pointer-events-none size-8 border-0 text-sidebar-foreground/70 opacity-0 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-foreground group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 max-[760px]:pointer-events-auto max-[760px]:opacity-100"
                        aria-label={isPinned ? "Unpin chat" : "Pin chat"}
                        aria-pressed={isPinned}
                        onClick={() => onTogglePinned?.(item.conversation_id)}
                      >
                        <Pin className={isPinned ? "fill-current" : ""} />
                      </Button>

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="pointer-events-none size-8 border-0 shadow-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 data-[state=open]:pointer-events-auto data-[state=open]:opacity-100 max-[760px]:pointer-events-auto max-[760px]:opacity-100"
                            aria-label={`${translate("sidebar.actionsFor")} ${item.title}`}
                          >
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuGroup>
                            <DropdownMenuItem
                              onSelect={() => {
                                setDraftTitle(item.title);
                                setEditingId(item.conversation_id);
                              }}
                            >
                              <Pencil />
                              {translate("sidebar.rename")}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              variant="destructive"
                              disabled={pendingId === item.conversation_id}
                              onSelect={() => void removeConversation(item)}
                            >
                              <Trash2 />
                              {translate("sidebar.delete")}
                            </DropdownMenuItem>
                          </DropdownMenuGroup>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
