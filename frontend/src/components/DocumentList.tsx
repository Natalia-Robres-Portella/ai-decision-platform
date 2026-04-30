// DocumentList — table of ingested documents with:
//  - Skeleton rows while loading (pure CSS animate-pulse, no library)
//  - Auto-polling while any document is "processing" (React Query refetchInterval)
//  - Checkbox per row to scope chat queries (Zustand store)
//  - Status badge that matches backend values: processing | completed | failed

import { useQuery } from "@tanstack/react-query";
import { CheckCircle, FileText, Loader, AlertCircle } from "lucide-react";
import { getDocuments } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import type { Document } from "@/types";

// ── Utilities ───────────────────────────────────────────────────────────────

function truncateFilename(name: string, maxLen = 40): string {
  if (name.length <= maxLen) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  return name.slice(0, maxLen - ext.length - 1) + "…" + ext;
}

function formatRelativeTime(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  const diffMin = Math.round(diffMs / 60_000);
  // Intl.RelativeTimeFormat gives us "2 minutes ago", "just now", etc.
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
    diffMin,
    "minute",
  );
}

// ── Status badge ────────────────────────────────────────────────────────────
//
// Uses ring-inset to avoid adding layout width — the ring sits inside
// the element's border-box. This is a common Tailwind pattern for tags.

const STATUS_STYLES = {
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  processing: "bg-amber-50 text-amber-700 ring-amber-600/20",
  failed: "bg-red-50 text-red-600 ring-red-600/20",
} as const;

const STATUS_LABELS = {
  completed: "Ready",
  processing: "Processing",
  failed: "Failed",
} as const;

function StatusBadge({ status }: { status: string }) {
  const style =
    STATUS_STYLES[status as keyof typeof STATUS_STYLES] ??
    "bg-gray-100 text-gray-600 ring-gray-400/20";
  const label =
    STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
    >
      {status === "processing" && <Loader size={10} className="animate-spin" />}
      {status === "completed" && <CheckCircle size={10} />}
      {status === "failed" && <AlertCircle size={10} />}
      {label}
    </span>
  );
}

// ── Skeleton rows (loading state) ───────────────────────────────────────────
//
// Pure CSS skeleton: animate-pulse + bg-gray-100 rectangles that mimic
// the shape of real content. No external library needed.
// The widths are varied (w-44, w-16, w-20, w-24) so rows don't look identical.

function SkeletonRow({ seed }: { seed: number }) {
  // Vary widths per row so skeletons don't look like a uniform grid
  const widths = ["w-44", "w-52", "w-40"];
  const nameWidth = widths[seed % widths.length];

  return (
    <tr className="border-b border-gray-100 last:border-0">
      <td className="py-3.5 pl-4 pr-2">
        <div className="h-4 w-4 rounded bg-gray-100 animate-pulse" />
      </td>
      <td className="py-3.5 pr-4">
        <div className="flex items-center gap-2">
          <div className="h-3.5 w-3.5 flex-shrink-0 rounded bg-gray-100 animate-pulse" />
          <div className={`h-3.5 rounded bg-gray-100 animate-pulse ${nameWidth}`} />
        </div>
      </td>
      <td className="py-3.5 pr-6 text-right">
        <div className="ml-auto h-3.5 w-14 rounded bg-gray-100 animate-pulse" />
      </td>
      <td className="py-3.5 pr-6 text-center">
        <div className="mx-auto h-5 w-20 rounded-full bg-gray-100 animate-pulse" />
      </td>
      <td className="py-3.5 pr-4 text-right">
        <div className="ml-auto h-3.5 w-24 rounded bg-gray-100 animate-pulse" />
      </td>
    </tr>
  );
}

// ── Document row ────────────────────────────────────────────────────────────

function DocumentRow({ doc }: { doc: Document }) {
  const { selectedDocumentIds, toggleDocument } = useChatStore();
  const isSelected = selectedDocumentIds.includes(doc.id);
  const isReady = doc.status === "completed";

  return (
    <tr
      className={[
        "border-b border-gray-100 last:border-0 transition-colors",
        isSelected ? "bg-blue-50/40" : "hover:bg-gray-50/60",
      ].join(" ")}
    >
      {/* Checkbox scopes chat queries to this document */}
      <td className="py-3.5 pl-4 pr-2">
        <input
          type="checkbox"
          checked={isSelected}
          disabled={!isReady}
          onChange={() => toggleDocument(doc.id)}
          title={
            isReady
              ? "Include in chat scope"
              : "Document must be ready before filtering"
          }
          className="h-4 w-4 cursor-pointer rounded border-gray-300 text-blue-600 focus:ring-blue-500 focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-40"
        />
      </td>

      {/* Filename */}
      <td className="py-3.5 pr-4">
        <div className="flex items-center gap-2">
          <FileText
            size={14}
            className="flex-shrink-0 text-slate-400"
          />
          <span
            className="text-sm text-slate-800"
            title={doc.filename}
          >
            {truncateFilename(doc.filename)}
          </span>
        </div>
      </td>

      {/* Chunks */}
      <td className="py-3.5 pr-6 text-right font-mono text-xs tabular-nums text-slate-500">
        {doc.num_chunks != null ? doc.num_chunks.toLocaleString() : "—"}
      </td>

      {/* Status */}
      <td className="py-3.5 pr-6 text-center">
        <StatusBadge status={doc.status} />
      </td>

      {/* Uploaded at */}
      <td className="py-3.5 pr-4 text-right text-xs text-slate-400">
        {formatRelativeTime(doc.created_at)}
      </td>
    </tr>
  );
}

// ── Empty state ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-200 py-14 text-center">
      <FileText size={22} className="mx-auto text-slate-300" />
      <p className="mt-3 text-sm font-medium text-slate-500">
        No documents ingested yet
      </p>
      <p className="mt-1 text-xs text-slate-400">
        Upload your first PDF above to get started.
      </p>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export function DocumentList() {
  const { data: documents = [], isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: getDocuments,
    // Automatically re-fetch every 3 s while any document is still processing.
    // React Query stops the interval the moment refetchInterval returns false.
    // Achieving this with useState + setInterval would require manual cleanup.
    refetchInterval: (query) => {
      const hasProcessing = query.state.data?.some(
        (d) => d.status === "processing",
      );
      return hasProcessing ? 3000 : false;
    },
  });

  const selectedCount = useChatStore((s) => s.selectedDocumentIds.length);

  return (
    <div>
      {/* Section header */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Ingested Documents
        </h2>
        <div className="flex items-center gap-3">
          {selectedCount > 0 && (
            <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700 ring-1 ring-blue-200">
              {selectedCount} selected for chat
            </span>
          )}
          {!isLoading && documents.length > 0 && (
            <span className="text-xs text-slate-400">
              {documents.length} total
            </span>
          )}
        </div>
      </div>

      {/* Empty state */}
      {!isLoading && documents.length === 0 && <EmptyState />}

      {/* Table */}
      {(isLoading || documents.length > 0) && (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-left">
            <thead className="border-b border-gray-100 bg-gray-50">
              <tr>
                <th className="py-2.5 pl-4 pr-2 w-10" aria-label="Select" />
                <th className="py-2.5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Filename
                </th>
                <th className="py-2.5 pr-6 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Chunks
                </th>
                <th className="py-2.5 pr-6 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Status
                </th>
                <th className="py-2.5 pr-4 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Uploaded
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? [0, 1, 2].map((i) => <SkeletonRow key={i} seed={i} />)
                : documents.map((doc) => (
                    <DocumentRow key={doc.id} doc={doc} />
                  ))}
            </tbody>
          </table>

          {!isLoading && documents.length > 0 && (
            <p className="border-t border-gray-100 px-4 py-2.5 text-xs text-slate-400">
              Check documents to scope chat queries to specific files. Only
              ready documents can be selected.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
