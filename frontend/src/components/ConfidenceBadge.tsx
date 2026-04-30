import type { ConfidenceLevel } from "@/types";

const STYLES: Record<ConfidenceLevel, string> = {
  high: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  low: "bg-red-50 text-red-600 ring-red-600/20",
};

const LABELS: Record<ConfidenceLevel, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

interface Props {
  level: ConfidenceLevel;
  className?: string;
}

export function ConfidenceBadge({ level, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[level]} ${className}`}
    >
      {LABELS[level]}
    </span>
  );
}
