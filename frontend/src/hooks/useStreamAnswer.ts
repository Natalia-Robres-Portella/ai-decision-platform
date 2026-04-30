// Custom hook that consumes the POST /ask/stream SSE endpoint.
//
// Why fetch instead of EventSource?
// The browser's built-in EventSource API only supports GET requests.
// Our streaming endpoint is POST (it needs a request body with the question).
// The fetch Streams API lets us read a ReadableStream from any request method,
// so we manually parse the SSE line protocol on top of it.
//
// SSE wire format (what the server sends):
//   data: {"type":"token","content":"Tesla"}\n\n
//   data: {"type":"sources","content":[{...}]}\n\n
//   data: [DONE]\n\n
//
// We buffer incomplete lines because a single fetch chunk may contain a
// partial SSE event if the network delivers data mid-line.

import { useCallback, useRef, useState } from "react";
import type { SourceReference, StreamEvent } from "@/types";

interface StreamState {
  answer: string;
  sources: SourceReference[];
  isStreaming: boolean;
  error: string | null;
}

const INITIAL: StreamState = {
  answer: "",
  sources: [],
  isStreaming: false,
  error: null,
};

export function useStreamAnswer() {
  const [state, setState] = useState<StreamState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const stream = useCallback(async (question: string, documentIds?: string[]) => {
    // Cancel any in-flight stream before starting a new one
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setState({ ...INITIAL, isStreaming: true });

    try {
      const response = await fetch("/api/v1/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          document_ids: documentIds?.length ? documentIds : null,
        }),
        signal: abortRef.current.signal,
      });

      if (!response.ok) throw new Error(`Server error: HTTP ${response.status}`);
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Append decoded chunk to buffer, then split on newlines.
        // A chunk may arrive mid-line, so we keep the last incomplete
        // fragment in the buffer for the next iteration.
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") return;

          const event = JSON.parse(payload) as StreamEvent;

          if (event.type === "token") {
            setState((s) => ({ ...s, answer: s.answer + event.content }));
          } else if (event.type === "sources") {
            setState((s) => ({ ...s, sources: event.content }));
          } else if (event.type === "error") {
            setState((s) => ({ ...s, error: event.content }));
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : "Stream failed",
      }));
    } finally {
      setState((s) => ({ ...s, isStreaming: false }));
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(INITIAL);
  }, []);

  return { ...state, stream, reset };
}
