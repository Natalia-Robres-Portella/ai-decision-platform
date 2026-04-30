// Centralised API layer — all network calls go through here.
//
// Why axios instead of bare fetch?
// - Automatic JSON serialisation/deserialisation
// - Interceptors: one place to add auth headers, log errors, or retry
// - Typed response generics: axios.get<T>() gives you T, not unknown
// - Better error objects: AxiosError carries response body, status, headers

import axios from "axios";
import type { AnswerResponse, Document, EvalReport, IngestResponse, QueryHistoryEntry } from "@/types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// ── Documents ──────────────────────────────────────────────────────────────

export async function getDocuments(): Promise<Document[]> {
  const res = await api.get<Document[]>("/documents");
  return res.data;
}

// onUploadProgress fires as bytes are sent to the server (0 → 100%).
// After it reaches 100% the server begins the pipeline (chunking + embedding),
// so the promise stays pending for several more seconds. The caller should
// show a "Processing…" state once percent hits 100.
export async function ingestDocument(
  file: File,
  onUploadProgress?: (percent: number) => void,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<IngestResponse>("/documents/ingest", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: onUploadProgress
      ? (e) => {
          const pct = Math.round((e.loaded * 100) / (e.total ?? e.loaded));
          onUploadProgress(Math.min(pct, 99)); // cap at 99 until server responds
        }
      : undefined,
  });
  return res.data;
}

// ── QA (non-streaming) ─────────────────────────────────────────────────────

export async function askQuestion(
  question: string,
  documentIds?: string[],
): Promise<AnswerResponse> {
  const res = await api.post<AnswerResponse>("/ask", {
    question,
    document_ids: documentIds?.length ? documentIds : null,
  });
  return res.data;
}

// ── History ────────────────────────────────────────────────────────────────

export async function getHistory(): Promise<QueryHistoryEntry[]> {
  const res = await api.get<QueryHistoryEntry[]>("/history");
  return res.data;
}

// ── Evaluation ─────────────────────────────────────────────────────────────

export async function runEvaluation(): Promise<EvalReport> {
  const res = await api.post<EvalReport>("/eval/run", null, {
    timeout: 300_000, // 5 min — eval runs ~10 questions × 4 LLM calls each
  });
  return res.data;
}
