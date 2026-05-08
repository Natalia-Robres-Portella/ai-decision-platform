// MessageList — renders the full conversation history plus the live streaming turn.
//
// Architecture:
//   - Completed messages come from Zustand (ChatPage commits them when streaming ends)
//   - The active streaming turn is passed as `streaming` props so the bubble updates
//     token-by-token without touching the store until the turn is complete
//   - Auto-scrolls to bottom on new messages and on each token arrival

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import type { ChatMessage } from "@/store/chatStore";
import type { SourceReference, ConfidenceLevel } from "@/types";

// ── Relevance badge ──────────────────────────────────────────────────────────

function RelevanceBadge({ score }: { score: number }) {
  const style =
    score > 0.8
      ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
      : score >= 0.6
        ? "bg-amber-50 text-amber-700 ring-amber-600/20"
        : "bg-red-50 text-red-600 ring-red-600/20";

  return (
    <span
      className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset ${style}`}
    >
      {(score * 100).toFixed(0)}%
    </span>
  );
}

// ── Collapsible sources section ──────────────────────────────────────────────

function SourcesSection({ sources }: { sources: SourceReference[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors hover:text-slate-600"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {sources.length} source{sources.length !== 1 ? "s" : ""}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((src, i) => (
            <div key={i} className="rounded-md bg-gray-50 p-2.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5">
                  <FileText size={11} className="flex-shrink-0 text-slate-400" />
                  <span className="truncate font-medium text-slate-600">{src.filename}</span>
                  {src.page_number != null && (
                    <span className="flex-shrink-0 text-slate-400">p.{src.page_number}</span>
                  )}
                </div>
                <RelevanceBadge score={src.relevance_score} />
              </div>
              {src.excerpt && (
                <p className="mt-1.5 line-clamp-3 leading-relaxed text-slate-500">
                  &quot;{src.excerpt}&quot;
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Typing indicator (three animated dots) ───────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-1">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-2 w-2 animate-bounce rounded-full bg-slate-300"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

// ── User bubble ──────────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-slate-900 px-4 py-2.5 text-sm text-white">
        {content}
      </div>
    </div>
  );
}

// ── Assistant bubble ─────────────────────────────────────────────────────────

interface AssistantBubbleProps {
  content: string;
  sources?: SourceReference[];
  confidence?: ConfidenceLevel;
  isStreaming?: boolean;
  error?: string | null;
}

function AssistantBubble({
  content,
  sources,
  confidence,
  isStreaming,
  error,
}: AssistantBubbleProps) {
  const showTypingIndicator = isStreaming && !content;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : showTypingIndicator ? (
          <TypingIndicator />
        ) : (
          <>
            {/* prose-sm gives markdown headings/lists/code their default styles */}
            <div className="prose prose-sm prose-slate max-w-none">
              <ReactMarkdown>{content}</ReactMarkdown>
              {isStreaming && (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-400" />
              )}
            </div>

            {!isStreaming && confidence && (
              <div className="mt-2">
                <ConfidenceBadge level={confidence} />
              </div>
            )}

            {!isStreaming && sources && sources.length > 0 && (
              <SourcesSection sources={sources} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center text-center">
      <div>
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <FileText size={20} className="text-slate-400" />
        </div>
        <h3 className="text-sm font-medium text-slate-700">Ask about your documents</h3>
        <p className="mt-1 text-xs text-slate-400">
          Upload PDFs on the Documents page, then ask questions here.
        </p>
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export interface StreamingState {
  question: string | null;
  answer: string;
  sources: SourceReference[];
  isStreaming: boolean;
  error: string | null;
}

interface MessageListProps {
  messages: ChatMessage[];
  streaming: StreamingState;
}

export function MessageList({ messages, streaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever a new message is added or a token arrives
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming.answer]);

  const isEmpty = messages.length === 0 && streaming.question === null;

  return (
    <div className="h-full overflow-y-auto">
      {isEmpty ? (
        <EmptyState />
      ) : (
        <div className="flex flex-col gap-6 px-6 py-6">
          {/* Completed turns */}
          {messages.map((msg) =>
            msg.role === "user" ? (
              <UserBubble key={msg.id} content={msg.content} />
            ) : (
              <AssistantBubble
                key={msg.id}
                content={msg.content}
                sources={msg.sources}
                confidence={msg.confidence}
                error={msg.error}
              />
            ),
          )}

          {/* Live streaming turn */}
          {streaming.question !== null && (
            <>
              <UserBubble content={streaming.question} />
              <AssistantBubble
                content={streaming.answer}
                sources={streaming.sources}
                isStreaming={streaming.isStreaming}
                error={streaming.error}
              />
            </>
          )}

          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
