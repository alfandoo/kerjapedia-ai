"use client";

import { useCallback, useEffect, useState, type SetStateAction } from "react";
import { useStoredSession } from "@/features/auth";
import { fetchConversations } from "./api";
import type { ConversationSummary } from "./types";

type History = { owner: string | undefined; items: ConversationSummary[]; confirmed: boolean };
// Shared only within this tab; switching accounts replaces the cached owner.
let cached: History | null = null;

export function useConversationHistory() {
  const owner = useStoredSession()?.user.user_id;
  const [history, setHistory] = useState<History>(() =>
    cached && cached.owner === owner && owner ? cached : { owner, items: [], confirmed: false }
  );
  const [busy, setHistoryLoading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const retryHistory = useCallback(() => setRevision(value => value + 1), []);
  const setConversations = useCallback((update: SetStateAction<ConversationSummary[]>) => {
    setHistory(previous => {
      const current = previous.owner === owner ? previous.items : [];
      const next = { owner, items: typeof update === "function" ? update(current) : update, confirmed: true };
      cached = next;
      return next;
    });
  }, [owner]);

  useEffect(() => {
    if (!owner) { cached = null; return; }
    if (cached?.owner !== owner) cached = null;
    const controller = new AbortController();
    // Keep the last confirmed list visible while revalidating on navigation.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFailure(null);
    void fetchConversations(controller.signal).then(items => {
      if (!controller.signal.aborted) setConversations(items);
    }).catch(() => {
      if (!controller.signal.aborted) setFailure(owner);
    });
    return () => controller.abort();
  }, [owner, revision, setConversations]);

  const sameOwner = history.owner === owner;
  const historyError = failure === owner && Boolean(owner);
  return {
    conversations: sameOwner ? history.items : [],
    setConversations,
    historyLoading: busy || ((!sameOwner || !history.confirmed) && !historyError),
    setHistoryLoading,
    historyError,
    retryHistory,
  };
}
