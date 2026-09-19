"use client";

import { useEffect, useRef, useState } from "react";

import { MessageSquare, MoreHorizontal, Pencil, Pin, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  error?: boolean;
  onRetry?: () => void;
  onConversationSelect?: (conversationId: string) => void;
  onNewConversation?: () => void;
  onConversationRename?: (conversationId: string, title: string) => Promise<void>;
  onConversationDelete?: (conversationId: string) => Promise<void>;
  historyEnabled?: boolean;
  showNewConversation?: boolean;
  emptyMessage?: string;
  showEmptyState?: boolean;
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
      className="min-h-8 min-w-0 justify-start rounded-none border-0 px-0.5 text-left shadow-none hover:bg-transparent"
      aria-current={isActive ? "page" : undefined}
      title={title}
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
  error = false,
  onRetry,
  onConversationSelect,
  onNewConversation,
  onConversationRename,
  onConversationDelete,
  historyEnabled = true,
  showNewConversation = true,
  emptyMessage,
  showEmptyState = true,
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
  const [confirmDeleteItem, setConfirmDeleteItem] = useState<ConversationSummary | null>(null);

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
    setPendingId(item.conversation_id);
    try {
      await onConversationDelete(item.conversation_id);
    } catch {
      return;
    } finally {
      setPendingId(null);
      setConfirmDeleteItem(null);
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
      {showTitle || showNewConversation ? (
        <div className="mb-1 flex min-h-9 items-center gap-1 px-0.5">
          {showTitle ? (
            <h2 className="min-w-0 flex-1 truncate text-xs font-semibold text-sidebar-foreground">
              {translate("sidebar.chatHistory")}
            </h2>
          ) : null}
          {showNewConversation ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 border-0 text-sidebar-foreground/70 shadow-none hover:bg-sidebar-accent hover:text-sidebar-foreground"
              onClick={onNewConversation}
              title={translate("sidebar.newChat")}
              aria-label={translate("sidebar.newChat")}
            >
              <Pencil className="size-4" />
            </Button>
          ) : null}
        </div>
      ) : null}

      <div
        className={cn(
          "min-w-0",
          !embedded &&
            "history-scroll-region min-h-0 flex-1 overflow-y-auto overscroll-contain pr-0.5"
        )}
        aria-busy={historyEnabled && loading}
      >
        {error && historyEnabled ? (
          <div className="px-3 py-3 text-xs text-muted-foreground" role="status">
            <p>{translate("sidebar.historyError")}</p>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 inline-flex min-h-11 items-center text-sidebar-foreground underline underline-offset-4"
              >
                {translate("sidebar.retryHistory")}
              </button>
            ) : null}
          </div>
        ) : null}
        {loading && historyEnabled ? (
          <div className="flex flex-col gap-2 px-0.5 py-1" role="status">
            <span className="sr-only">{translate("sidebar.loadingHistory")}</span>
            <Skeleton className="h-3 w-16" />
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-8 w-full rounded-lg" />
            ))}
          </div>
        ) : null}

        {!loading && !error && historyEnabled && showEmptyState && conversations.length === 0 ? (
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
                        className="text-[10px] text-sidebar-foreground"
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
                          ? "grid-cols-[20px_minmax(0,1fr)_0_0] group-hover:grid-cols-[20px_minmax(0,1fr)_44px_44px] group-focus-within:grid-cols-[20px_minmax(0,1fr)_44px_44px] max-[760px]:grid-cols-[20px_minmax(0,1fr)_44px_44px]"
                          : "grid-cols-[minmax(0,1fr)_0_0] group-hover:grid-cols-[minmax(0,1fr)_44px_44px] group-focus-within:grid-cols-[minmax(0,1fr)_44px_44px] max-[760px]:grid-cols-[minmax(0,1fr)_44px_44px]"
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
                        className="pointer-events-none size-8 border-0 text-sidebar-foreground/70 opacity-0 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 max-[760px]:pointer-events-auto max-[760px]:opacity-100"
                        aria-label={
                          isPinned ? translate("history.unpinChat") : translate("history.pinChat")
                        }
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
                            className="pointer-events-none size-8 border-0 shadow-none opacity-0 transition hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 data-[state=open]:pointer-events-auto data-[state=open]:opacity-100 max-[760px]:pointer-events-auto max-[760px]:opacity-100"
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
                              onSelect={() => setConfirmDeleteItem(item)}
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
      <Dialog
        open={confirmDeleteItem !== null}
        onOpenChange={(open) => {
          if (!open && pendingId === null) setConfirmDeleteItem(null);
        }}
      >
        <DialogContent
          className="w-[calc(100vw_-_2rem)] gap-3 sm:max-w-[320px]"
          showCloseButton={pendingId === null}
        >
          <DialogHeader>
            <DialogTitle>{translate("sidebar.deleteConfirm")}</DialogTitle>
            <DialogDescription>
              “{confirmDeleteItem?.title}”? {translate("sidebar.deleteWarning")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={pendingId !== null}>
                {translate("sidebar.cancel")}
              </Button>
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              disabled={pendingId !== null}
              onClick={() => {
                if (confirmDeleteItem) void removeConversation(confirmDeleteItem);
              }}
            >
              {translate("sidebar.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
