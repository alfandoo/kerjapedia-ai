import type { AnswerPayload } from "@/lib/types";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  answer?: AnswerPayload;
  streaming?: boolean;
  status?: string;
};
