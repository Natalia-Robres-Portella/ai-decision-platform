// TypeScript interfaces that mirror the backend Pydantic schemas exactly.
// When the backend schema changes, update here too — these are the single
// source of truth for what the API sends and receives on the frontend.

export type ConfidenceLevel = "high" | "medium" | "low";
// Values match the backend exactly — see app/api/routes/ingestion.py
export type DocumentStatus = "processing" | "completed" | "failed";

// ── Documents ──────────────────────────────────────────────────────────────

export interface Document {
  id: string;
  filename: string;
  status: DocumentStatus;
  num_chunks: number | null;
  created_at: string;
}

export interface IngestResponse {
  document_id: string;
  filename: string;
  num_chunks: number; // pipeline is synchronous — chunks are known on response
  status: string;
}

// ── Retrieval & QA ─────────────────────────────────────────────────────────

export interface SourceReference {
  filename: string;
  page_number: number;
  relevance_score: number;
  excerpt: string;
}

export interface AnswerResponse {
  query: string;
  answer: string;
  sources: SourceReference[];
  confidence: ConfidenceLevel;
  model_used: string;
  tokens_used: number;
}

// ── History ────────────────────────────────────────────────────────────────

export interface QueryHistoryEntry {
  id: string;
  question: string;
  answer: string;
  confidence: string;
  tokens_used: number;
  sources: SourceReference[] | null;
  created_at: string;
}

// ── SSE stream events from POST /ask/stream ────────────────────────────────
//
// The stream sends newline-delimited SSE events:
//   data: {"type": "token",   "content": "Tesla's"}
//   data: {"type": "sources", "content": [{...}]}
//   data: {"type": "error",   "content": "No relevant..."}
//   data: [DONE]

export interface StreamTokenEvent {
  type: "token";
  content: string;
}

export interface StreamSourcesEvent {
  type: "sources";
  content: SourceReference[];
}

export interface StreamErrorEvent {
  type: "error";
  content: string;
}

export type StreamEvent = StreamTokenEvent | StreamSourcesEvent | StreamErrorEvent;

// ── Evaluation ─────────────────────────────────────────────────────────────

export interface EvalQuestionResult {
  id: string;
  question: string;
  answer: string;
  faithfulness: number;        // 0–1
  faithfulness_supported: number;
  faithfulness_total: number;
  relevance: number;           // 0–1 normalised
  relevance_raw: number;       // 1–5
  completeness: number;        // 0–1 normalised
  completeness_raw: number;    // 1–5
  completeness_explanation: string;
  retrieval_latency_ms: number;
  total_latency_ms: number;
  error?: string | null;
}

export interface EvalReport {
  timestamp: string;
  total_questions: number;
  avg_faithfulness: number;
  avg_relevance: number;
  avg_completeness: number;
  avg_retrieval_latency_ms: number;
  avg_total_latency_ms: number;
  results: EvalQuestionResult[];
}
