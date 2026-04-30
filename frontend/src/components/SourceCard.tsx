import { FileText } from "lucide-react";
import type { SourceReference } from "@/types";

interface Props {
  source: SourceReference;
  rank: number;
}

export function SourceCard({ source, rank }: Props) {
  const score = Math.round(source.relevance_score * 100);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-[10px] font-semibold text-slate-600">
            {rank}
          </span>
          <FileText size={13} className="flex-shrink-0 text-slate-400" />
          <span className="truncate text-xs font-medium text-slate-700">
            {source.filename}
          </span>
        </div>
        {/* Relevance score bar */}
        <div className="flex flex-shrink-0 items-center gap-1.5">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-blue-500"
              style={{ width: `${score}%` }}
            />
          </div>
          <span className="text-[11px] tabular-nums text-slate-400">{score}%</span>
        </div>
      </div>

      {/* Page */}
      <p className="mt-1.5 pl-9 text-[11px] text-slate-400">
        Page {source.page_number}
      </p>

      {/* Excerpt */}
      <p className="mt-2 pl-9 text-xs leading-relaxed text-slate-600 line-clamp-3">
        {source.excerpt}
      </p>
    </div>
  );
}
