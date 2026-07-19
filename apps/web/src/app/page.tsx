"use client";

import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ChatWorkspace } from "@/components/chat-workspace";
import { SourcePanel } from "@/components/source-panel";
import { fallbackCitation } from "@/lib/sample-data";
import type { Citation } from "@/lib/types";

export default function Home() {
  const [citations, setCitations] = useState<Citation[]>([fallbackCitation]);
  const [question, setQuestion] = useState("Hak cuti tahunan berapa hari?");

  return (
    <AppShell rightPanel={<SourcePanel citations={citations} question={question} />}>
      <ChatWorkspace
        onCitationsChange={(nextCitations, nextQuestion) => {
          setCitations(nextCitations.length > 0 ? nextCitations : [fallbackCitation]);
          setQuestion(nextQuestion);
        }}
      />
    </AppShell>
  );
}
