// DocumentFilter — collapsible bar that lets the user scope queries to specific documents.
//
// Reads selected IDs from Zustand, fetches document names from React Query
// (the documents query is already cached from IngestPage so no extra request).
// Only "completed" documents can be toggled — processing/failed ones are shown
// but disabled so the user can see what's there without getting confused.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, SlidersHorizontal } from "lucide-react";
import { getDocuments } from "@/services/api";
import { useChatStore } from "@/store/chatStore";

export function DocumentFilter() {
  const [open, setOpen] = useState(false);
  const { selectedDocumentIds, toggleDocument, clearSelection } = useChatStore();

  const { data: documents = [] } = useQuery({
    queryKey: ["documents"],
    queryFn: getDocuments,
  });

  const count = selectedDocumentIds.length;

  return (
    <div className="flex-shrink-0 border-b border-gray-100 bg-gray-50/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-6 py-2.5 text-left text-xs text-slate-500 transition-colors hover:text-slate-700"
      >
        <SlidersHorizontal size={12} className="flex-shrink-0" />
        <span className="flex-1 font-medium">
          {count === 0
            ? "Searching all documents"
            : `Searching in ${count} document${count !== 1 ? "s" : ""}`}
        </span>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>

      {open && (
        <div className="px-6 pb-3">
          {documents.length === 0 ? (
            <p className="text-xs text-slate-400">
              No documents uploaded yet. Go to the Documents page to add some.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {documents.map((doc) => {
                const isSelected = selectedDocumentIds.includes(doc.id);
                const isReady = doc.status === "completed";

                return (
                  <button
                    key={doc.id}
                    onClick={() => isReady && toggleDocument(doc.id)}
                    disabled={!isReady}
                    title={isReady ? undefined : "Document still processing"}
                    className={[
                      "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                      isSelected
                        ? "bg-blue-100 text-blue-700 ring-1 ring-blue-300"
                        : isReady
                          ? "bg-white text-slate-600 ring-1 ring-gray-200 hover:ring-gray-300"
                          : "cursor-not-allowed bg-white text-slate-400 ring-1 ring-gray-100 opacity-50",
                    ].join(" ")}
                  >
                    {doc.filename}
                  </button>
                );
              })}

              {count > 0 && (
                <button
                  onClick={clearSelection}
                  className="text-xs text-slate-400 transition-colors hover:text-slate-600"
                >
                  Clear all
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
