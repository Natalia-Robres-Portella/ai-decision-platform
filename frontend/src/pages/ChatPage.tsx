// ChatPage — streaming conversation interface.
//
// State model:
//   Zustand `messages`       → completed turns (persists for the session, resets on reload)
//   `pendingQuestion`        → the question currently being answered (local state)
//   `useStreamAnswer` hook   → live SSE state: answer tokens, sources, isStreaming, error
//
// Flow for a single turn:
//   1. User submits → set pendingQuestion, call stream()
//   2. As tokens arrive, AssistantBubble in MessageList updates live
//   3. When isStreaming flips to false → commit (user msg + assistant msg) to Zustand,
//      clear pendingQuestion, reset hook
//
// Why fetch instead of axios for streaming?
// axios buffers the entire response before resolving the promise, which defeats SSE.
// fetch's ReadableStream gives us token-by-token access. See useStreamAnswer for details.

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { useStreamAnswer } from "@/hooks/useStreamAnswer";
import { useChatStore } from "@/store/chatStore";
import { MessageList } from "@/components/chat/MessageList";
import { MessageInput } from "@/components/chat/MessageInput";
import { DocumentFilter } from "@/components/chat/DocumentFilter";
import type { ConfidenceLevel } from "@/types";
import type { StreamingState } from "@/components/chat/MessageList";

export function ChatPage() {
  const [input, setInput] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  const { answer, sources, isStreaming, error, stream, reset } = useStreamAnswer();
  const { selectedDocumentIds, messages, addMessages, clearMessages } = useChatStore();

  const handleSubmit = useCallback(() => {
    const q = input.trim();
    if (!q || isStreaming) return;
    setPendingQuestion(q);
    setInput("");
    stream(q, selectedDocumentIds);
  }, [input, isStreaming, selectedDocumentIds, stream]);

  // When streaming ends, commit the completed turn to the Zustand store.
  // This fires only when isStreaming transitions true → false while there
  // is an active pendingQuestion and we actually received content.
  useEffect(() => {
    if (isStreaming || pendingQuestion === null) return;
    if (!answer && !error) return;

    const topScore = sources[0]?.relevance_score ?? 0;
    const confidence: ConfidenceLevel =
      topScore > 0.8 ? "high" : topScore >= 0.6 ? "medium" : "low";

    addMessages([
      {
        id: crypto.randomUUID(),
        role: "user",
        content: pendingQuestion,
        timestamp: new Date().toISOString(),
      },
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: answer,
        sources: sources.length > 0 ? sources : undefined,
        confidence: sources.length > 0 ? confidence : undefined,
        error: error ?? undefined,
        timestamp: new Date().toISOString(),
      },
    ]);

    setPendingQuestion(null);
    reset();
  }, [isStreaming, pendingQuestion, answer, sources, error, addMessages, reset]);

  const streaming: StreamingState = {
    question: pendingQuestion,
    answer,
    sources,
    isStreaming,
    error,
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center justify-between border-b border-gray-100 bg-white px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-slate-900">Chat</h1>
          <p className="text-xs text-slate-400">
            Grounded answers from your ingested documents · citations included
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => {
              clearMessages();
              reset();
            }}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-slate-400 transition-colors hover:bg-gray-100 hover:text-slate-600"
          >
            <Trash2 size={13} />
            Clear conversation
          </button>
        )}
      </div>

      {/* Document scope filter */}
      <DocumentFilter />

      {/* Conversation — takes remaining vertical space and scrolls internally */}
      <div className="min-h-0 flex-1">
        <MessageList messages={messages} streaming={streaming} />
      </div>

      {/* Input bar */}
      <MessageInput
        value={input}
        onChange={setInput}
        onSubmit={handleSubmit}
        isDisabled={isStreaming}
      />
    </div>
  );
}
