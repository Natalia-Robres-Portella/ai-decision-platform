// EvalPage — automated RAG pipeline quality dashboard.
//
// Metrics explained (for interviews):
//   Faithfulness   → hallucination rate: what % of answer sentences are
//                    grounded in retrieved sources (LLM-as-judge)
//   Relevance      → retrieval quality: did we pull the right chunks? (1-5)
//   Completeness   → answer coverage: did we address all aspects? (1-5)
//   Latency        → retrieval + embedding time vs total response time
//
// The evaluation runs server-side (~30-60 s). The UI shows a progress
// indicator during the run and renders results in a sortable table.

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Play, Loader, AlertCircle, CheckCircle, Info } from "lucide-react";
import { runEvaluation } from "@/services/api";
import type { EvalReport, EvalQuestionResult } from "@/types";

// ── Shared helpers ────────────────────────────────────────────────────────────

function pctLabel(score: number): string {
  return `${(score * 100).toFixed(0)}%`;
}

function scoreColor(score: number, scale: "pct" | "1-5"): string {
  const norm = scale === "pct" ? score : (score - 1) / 4;
  if (norm >= 0.8) return "text-emerald-600";
  if (norm >= 0.6) return "text-amber-600";
  return "text-red-600";
}

function scoreBg(score: number, scale: "pct" | "1-5"): string {
  const norm = scale === "pct" ? score : (score - 1) / 4;
  if (norm >= 0.8) return "bg-emerald-50 text-emerald-700 ring-emerald-600/20";
  if (norm >= 0.6) return "bg-amber-50 text-amber-700 ring-amber-600/20";
  return "bg-red-50 text-red-600 ring-red-600/20";
}

// ── Score pill ────────────────────────────────────────────────────────────────

function ScorePill({ value, label, scale }: { value: number; label: string; scale: "pct" | "1-5" }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${scoreBg(value, scale)}`}
    >
      {label}
    </span>
  );
}

// ── Mini bar ──────────────────────────────────────────────────────────────────

function MiniBar({ value, scale }: { value: number; scale: "pct" | "1-5" }) {
  const norm = scale === "pct" ? value : (value - 1) / 4;
  const color =
    norm >= 0.8 ? "bg-emerald-500" : norm >= 0.6 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${norm * 100}%` }} />
      </div>
    </div>
  );
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCard({
  label,
  value,
  display,
  scale,
  description,
}: {
  label: string;
  value: number;
  display: string;
  scale: "pct" | "1-5";
  description: string;
}) {
  const norm = scale === "pct" ? value : (value - 1) / 4;
  const ringColor =
    norm >= 0.8
      ? "border-emerald-200 bg-emerald-50"
      : norm >= 0.6
        ? "border-amber-200 bg-amber-50"
        : "border-red-200 bg-red-50";

  return (
    <div className={`rounded-lg border p-5 ${ringColor}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${scoreColor(value, scale)}`}>
        {display}
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/60">
        <div
          className={`h-full rounded-full ${norm >= 0.8 ? "bg-emerald-500" : norm >= 0.6 ? "bg-amber-400" : "bg-red-400"}`}
          style={{ width: `${norm * 100}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">{description}</p>
    </div>
  );
}

// ── Results table ─────────────────────────────────────────────────────────────

function ResultsTable({ results }: { results: EvalQuestionResult[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="w-full text-left">
        <thead className="border-b border-gray-100 bg-gray-50">
          <tr>
            <th className="py-3 pl-5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Question
            </th>
            <th className="py-3 pr-4 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
              Faithfulness
            </th>
            <th className="py-3 pr-4 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
              Relevance
            </th>
            <th className="py-3 pr-4 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
              Completeness
            </th>
            <th className="py-3 pr-5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
              Latency
            </th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <>
              <tr
                key={r.id}
                className="cursor-pointer border-b border-gray-100 transition-colors last:border-0 hover:bg-gray-50/60"
                onClick={() => setExpanded(expanded === r.id ? null : r.id)}
              >
                <td className="py-3.5 pl-5 pr-4">
                  {r.error ? (
                    <div className="flex items-center gap-2">
                      <AlertCircle size={13} className="flex-shrink-0 text-red-400" />
                      <span className="text-sm text-red-600">{r.question}</span>
                    </div>
                  ) : (
                    <span className="text-sm text-slate-700">{r.question}</span>
                  )}
                </td>

                {r.error ? (
                  <td colSpan={4} className="py-3.5 pr-5 text-right text-xs text-red-500">
                    {r.error}
                  </td>
                ) : (
                  <>
                    <td className="py-3.5 pr-4">
                      <div className="flex flex-col items-center gap-1">
                        <ScorePill
                          value={r.faithfulness}
                          label={pctLabel(r.faithfulness)}
                          scale="pct"
                        />
                        <MiniBar value={r.faithfulness} scale="pct" />
                      </div>
                    </td>
                    <td className="py-3.5 pr-4">
                      <div className="flex flex-col items-center gap-1">
                        <ScorePill
                          value={r.relevance_raw}
                          label={`${r.relevance_raw.toFixed(1)}/5`}
                          scale="1-5"
                        />
                        <MiniBar value={r.relevance_raw} scale="1-5" />
                      </div>
                    </td>
                    <td className="py-3.5 pr-4">
                      <div className="flex flex-col items-center gap-1">
                        <ScorePill
                          value={r.completeness_raw}
                          label={`${r.completeness_raw.toFixed(1)}/5`}
                          scale="1-5"
                        />
                        <MiniBar value={r.completeness_raw} scale="1-5" />
                      </div>
                    </td>
                    <td className="py-3.5 pr-5 text-right font-mono text-xs tabular-nums text-slate-500">
                      {r.total_latency_ms.toFixed(0)} ms
                    </td>
                  </>
                )}
              </tr>

              {/* Expanded detail row */}
              {expanded === r.id && !r.error && (
                <tr key={`${r.id}-detail`} className="border-b border-gray-100 bg-slate-50 last:border-0">
                  <td colSpan={5} className="px-5 py-4">
                    <div className="grid grid-cols-2 gap-6 text-xs">
                      <div>
                        <p className="mb-1 font-semibold text-slate-500">Answer snippet</p>
                        <p className="leading-relaxed text-slate-600">
                          {r.answer.slice(0, 300)}{r.answer.length > 300 ? "…" : ""}
                        </p>
                      </div>
                      <div>
                        <p className="mb-1 font-semibold text-slate-500">Completeness note</p>
                        <p className="leading-relaxed text-slate-600">
                          {r.completeness_explanation || "—"}
                        </p>
                        {r.faithfulness_total > 0 && (
                          <p className="mt-2 text-slate-400">
                            Faithfulness: {r.faithfulness_supported}/{r.faithfulness_total} sentences
                            grounded in sources
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
      <p className="border-t border-gray-100 px-5 py-2.5 text-xs text-slate-400">
        Click a row to expand answer details and completeness notes.
      </p>
    </div>
  );
}

// ── Empty / loading states ────────────────────────────────────────────────────

function RunButton({ onClick, isLoading }: { onClick: () => void; isLoading: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
      <div>
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
          {isLoading ? (
            <Loader size={22} className="animate-spin text-slate-500" />
          ) : (
            <CheckCircle size={22} className="text-slate-400" />
          )}
        </div>
        <h3 className="text-sm font-medium text-slate-700">
          {isLoading ? "Evaluating…" : "RAG Evaluation Suite"}
        </h3>
        <p className="mt-1 max-w-xs text-xs text-slate-400">
          {isLoading
            ? "Running 10 questions through the full pipeline. Faithfulness, relevance, and completeness are scored by GPT-4o-mini. Takes ~30–60 s."
            : "Automatically measures hallucination rate, retrieval quality, and answer completeness across a fixed test set."}
        </p>
      </div>

      {!isLoading && (
        <button
          onClick={onClick}
          className="flex items-center gap-2 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
        >
          <Play size={15} />
          Run Evaluation
        </button>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Info size={12} />
          Each question: retrieve → generate → 3 LLM judge calls
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function EvalPage() {
  const [report, setReport] = useState<EvalReport | null>(null);

  const { mutate, isPending, error } = useMutation({
    mutationFn: runEvaluation,
    onSuccess: (data) => setReport(data),
  });

  const errMsg =
    error instanceof Error ? error.message : error ? "Evaluation failed." : null;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center justify-between border-b border-gray-100 bg-white px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-slate-900">Evaluation</h1>
          <p className="text-xs text-slate-400">
            Automated RAG quality metrics · faithfulness · relevance · completeness
          </p>
        </div>
        {report && (
          <button
            onClick={() => mutate()}
            disabled={isPending}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            {isPending ? (
              <Loader size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            Re-run
          </button>
        )}
      </div>

      {/* Error banner */}
      {errMsg && (
        <div className="flex items-center gap-2 border-b border-red-100 bg-red-50 px-6 py-3 text-sm text-red-700">
          <AlertCircle size={15} className="flex-shrink-0" />
          {errMsg}
        </div>
      )}

      {/* Content */}
      <div className="flex min-h-0 flex-1 flex-col overflow-auto px-6 py-6">
        {!report ? (
          <RunButton onClick={() => mutate()} isLoading={isPending} />
        ) : (
          <div className="space-y-8">
            {/* Summary cards */}
            <div>
              <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                Summary · {report.total_questions} questions ·{" "}
                {new Date(report.timestamp).toLocaleString()}
              </h2>
              <div className="grid grid-cols-4 gap-4">
                <SummaryCard
                  label="Faithfulness"
                  value={report.avg_faithfulness}
                  display={pctLabel(report.avg_faithfulness)}
                  scale="pct"
                  description="Sentences grounded in sources"
                />
                <SummaryCard
                  label="Relevance"
                  value={report.avg_relevance}
                  display={`${report.avg_relevance.toFixed(2)}/5`}
                  scale="1-5"
                  description="Retrieval chunk quality"
                />
                <SummaryCard
                  label="Completeness"
                  value={report.avg_completeness}
                  display={`${report.avg_completeness.toFixed(2)}/5`}
                  scale="1-5"
                  description="Answer coverage"
                />
                <div className="rounded-lg border border-gray-200 bg-white p-5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Latency
                  </p>
                  <p className="mt-1 text-3xl font-bold tabular-nums text-slate-700">
                    {report.avg_total_latency_ms.toFixed(0)}
                    <span className="ml-1 text-base font-normal text-slate-400">ms</span>
                  </p>
                  <p className="mt-3 text-xs text-slate-400">
                    Retrieval: {report.avg_retrieval_latency_ms.toFixed(0)} ms avg
                  </p>
                  <p className="text-xs text-slate-400">Total: {report.avg_total_latency_ms.toFixed(0)} ms avg</p>
                </div>
              </div>
            </div>

            {/* Per-question table */}
            <div>
              <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                Per-question breakdown
              </h2>
              <ResultsTable results={report.results} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
