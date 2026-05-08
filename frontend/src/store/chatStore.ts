// Global UI state managed by Zustand.
//
// Why Zustand for this, not React Query or useState?
//
// React Query is for SERVER state (data that lives on the backend and can
// become stale). Zustand is for CLIENT state (UI choices that have no
// backend equivalent).
//
// Why not useState?
// selectedDocumentIds needs to be shared across two components: the
// DocumentList in IngestPage (checkboxes) and the ChatPage input (filter
// pills). Lifting this to a common ancestor would mean threading it through
// the Router — clumsy. Zustand lets both components read/write it directly.
//
// messages holds the completed conversation history for the session.
// It lives here (not React Query) because there is no server-side session —
// history is purely in-memory and resets on page reload by design.

import { create } from "zustand";
import type { SourceReference, ConfidenceLevel } from "@/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceReference[];
  confidence?: ConfidenceLevel;
  error?: string;
  timestamp: string;
}

interface ChatStore {
  // IDs of documents the user wants to scope their queries to.
  // Empty = search across all documents.
  selectedDocumentIds: string[];
  toggleDocument: (id: string) => void;
  clearSelection: () => void;

  // In-session conversation history. Resets on page reload.
  messages: ChatMessage[];
  addMessages: (msgs: ChatMessage[]) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  selectedDocumentIds: [],

  toggleDocument: (id) =>
    set((state) => ({
      selectedDocumentIds: state.selectedDocumentIds.includes(id)
        ? state.selectedDocumentIds.filter((d) => d !== id)
        : [...state.selectedDocumentIds, id],
    })),

  clearSelection: () => set({ selectedDocumentIds: [] }),

  messages: [],

  addMessages: (msgs) => set((state) => ({ messages: [...state.messages, ...msgs] })),

  clearMessages: () => set({ messages: [] }),
}));
