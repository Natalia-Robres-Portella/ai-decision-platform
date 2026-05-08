// MessageInput — auto-growing textarea with keyboard shortcuts.
//
// Growth cap: 4 lines (~96px at 24px line-height). Beyond that, the textarea
// becomes scrollable internally so the input bar never takes over the screen.
//
// Keyboard contract:
//   Enter            → submit (calls onSubmit)
//   Shift + Enter    → inserts a newline (browser default, no special handling)

import { useEffect, useRef } from "react";
import { ArrowRight, Loader } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isDisabled: boolean;
}

export function MessageInput({ value, onChange, onSubmit, isDisabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // 4 lines × 24px line-height + 24px padding ≈ 96px
    el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="flex-shrink-0 border-t border-gray-100 bg-white px-6 py-4">
      {isDisabled && (
        <p className="mb-2 flex items-center gap-1.5 text-xs text-slate-400">
          <Loader size={11} className="animate-spin" />
          Analyzing documents…
        </p>
      )}
      <div className="flex items-end gap-3">
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          placeholder="Ask anything about your documents… (Enter to send, Shift+Enter for newline)"
          className="flex-1 resize-none rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-blue-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-60"
        />
        <button
          onClick={onSubmit}
          disabled={!value.trim() || isDisabled}
          aria-label="Send message"
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isDisabled ? <Loader size={16} className="animate-spin" /> : <ArrowRight size={16} />}
        </button>
      </div>
    </div>
  );
}
