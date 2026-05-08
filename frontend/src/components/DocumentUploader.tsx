// DocumentUploader — three-phase upload flow:
//
//   IDLE          → user hasn't selected a file yet
//   FILE_SELECTED → file chosen (drag or picker) but not uploaded
//   UPLOADING     → bytes in flight to server (real progress via axios)
//   PROCESSING    → bytes received, server running chunking + embedding
//   SUCCESS       → API responded with filename + num_chunks
//   ERROR         → API returned an error
//
// The component owns its own mutation (not lifted to IngestPage) because it
// manages progress state that lives alongside the mutation lifecycle.
// It invalidates the ['documents'] React Query cache on success so
// DocumentList refreshes without IngestPage wiring anything.

import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle, FileText, Loader, Upload, X } from "lucide-react";
import { ingestDocument } from "@/services/api";
import type { IngestResponse } from "@/types";

// ── Utilities ───────────────────────────────────────────────────────────────

const MAX_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function truncateFilename(name: string, maxLen = 40): string {
  if (name.length <= maxLen) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  return name.slice(0, maxLen - ext.length - 1) + "…" + ext;
}

function validate(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return `"${truncateFilename(file.name)}" is not a PDF file. Only PDF files are accepted.`;
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File is too large (${formatSize(file.size)}). Maximum allowed size is 50 MB.`;
  }
  return null;
}

// ── Drop zone (idle state) ──────────────────────────────────────────────────

interface DropZoneProps {
  onFile: (file: File) => void;
}

function DropZone({ onFile }: DropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback(
    (file: File | undefined) => {
      if (file) onFile(file);
    },
    [onFile]
  );

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Drop a PDF here or click to browse"
      onDragOver={(e) => {
        e.preventDefault(); // required — without this, onDrop won't fire
        setIsDragOver(true);
      }}
      onDragLeave={(e) => {
        // Only clear when leaving the zone itself, not a child element
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setIsDragOver(false);
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragOver(false);
        pick(e.dataTransfer.files[0]);
      }}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
      className={[
        "flex cursor-pointer select-none flex-col items-center justify-center rounded-lg border-2 px-6 py-14 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        isDragOver
          ? "border-blue-500 bg-blue-50"
          : "border-dashed border-gray-300 bg-white hover:border-gray-400 hover:bg-gray-50",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = ""; // allow re-selecting the same file
        }}
      />

      <Upload
        size={28}
        strokeWidth={1.5}
        className={isDragOver ? "text-blue-500" : "text-slate-300"}
      />
      <p className="mt-3 text-sm font-medium text-slate-600">
        {isDragOver ? "Drop to select" : "Drop a PDF here or click to browse"}
      </p>
      <p className="mt-1 text-xs text-slate-400">PDF only · max 50 MB</p>
    </div>
  );
}

// ── File preview (file selected, not yet uploaded) ──────────────────────────

interface PreviewProps {
  file: File;
  onClear: () => void;
  onUpload: () => void;
  validationError: string | null;
}

function FilePreview({ file, onClear, onUpload, validationError }: PreviewProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-slate-100">
          <FileText size={18} className="text-slate-500" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-800">{truncateFilename(file.name)}</p>
          <p className="mt-0.5 text-xs text-slate-400">{formatSize(file.size)}</p>
        </div>
        <button
          onClick={onClear}
          className="rounded p-1 text-slate-400 hover:bg-gray-100 hover:text-slate-600 transition-colors"
          aria-label="Remove file"
        >
          <X size={16} />
        </button>
      </div>

      {validationError ? (
        <p className="mt-4 flex items-start gap-2 rounded-md bg-red-50 px-3 py-2.5 text-xs text-red-600">
          <AlertCircle size={13} className="mt-0.5 flex-shrink-0" />
          {validationError}
        </p>
      ) : (
        <div className="mt-4 flex justify-end">
          <button
            onClick={onUpload}
            className="flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
          >
            <Upload size={14} />
            Upload PDF
          </button>
        </div>
      )}
    </div>
  );
}

// ── In-progress states ──────────────────────────────────────────────────────

function UploadProgress({ filename, percent }: { filename: string; percent: number }) {
  // percent is capped at 99 while bytes are in flight.
  // Once we hit 99, the server is running the pipeline — show a different message.
  const isServerProcessing = percent >= 99;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-slate-100">
          <Loader size={16} className="animate-spin text-slate-500" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-slate-700">{truncateFilename(filename)}</p>
          <p className="mt-0.5 text-xs text-slate-400">
            {isServerProcessing ? "Processing chunks and embeddings…" : `Uploading… ${percent}%`}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-4">
        <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
          <div
            className={[
              "h-full rounded-full transition-all duration-300",
              isServerProcessing ? "animate-pulse bg-blue-400" : "bg-blue-500",
            ].join(" ")}
            style={{ width: isServerProcessing ? "100%" : `${percent}%` }}
          />
        </div>
        <div className="mt-1.5 flex justify-between text-[11px] text-slate-400">
          <span>{isServerProcessing ? "Chunking + embedding" : "Uploading"}</span>
          {!isServerProcessing && <span className="tabular-nums">{percent}%</span>}
        </div>
      </div>
    </div>
  );
}

// ── Success state ───────────────────────────────────────────────────────────

function SuccessPanel({ result, onReset }: { result: IngestResponse; onReset: () => void }) {
  return (
    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-5">
      <div className="flex items-start gap-3">
        <CheckCircle size={20} className="mt-0.5 flex-shrink-0 text-emerald-500" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-emerald-800">
            {truncateFilename(result.filename)}
          </p>
          <p className="mt-1 text-xs text-emerald-600">
            {result.num_chunks.toLocaleString()} chunks created and indexed · ready to query
          </p>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          onClick={onReset}
          className="text-xs font-medium text-emerald-700 hover:text-emerald-900 transition-colors"
        >
          Upload another document
        </button>
      </div>
    </div>
  );
}

// ── Error state ─────────────────────────────────────────────────────────────

function ErrorPanel({ message, onReset }: { message: string; onReset: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-5">
      <div className="flex items-start gap-3">
        <AlertCircle size={20} className="mt-0.5 flex-shrink-0 text-red-500" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-red-800">Upload failed</p>
          <p className="mt-1 text-xs text-red-600">{message}</p>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          onClick={onReset}
          className="text-xs font-medium text-red-700 hover:text-red-900 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export function DocumentUploader() {
  const queryClient = useQueryClient();
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (file: File) => ingestDocument(file, setUploadPercent),
    onSuccess: () => {
      // Refresh document list automatically — DocumentList reads ['documents']
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const handleFileChosen = useCallback(
    (file: File) => {
      setValidationError(validate(file));
      setPendingFile(file);
      mutation.reset();
    },
    [mutation]
  );

  const handleUpload = useCallback(() => {
    if (!pendingFile) return;
    setUploadPercent(0);
    mutation.mutate(pendingFile);
  }, [pendingFile, mutation]);

  const handleReset = useCallback(() => {
    setPendingFile(null);
    setUploadPercent(0);
    setValidationError(null);
    mutation.reset();
  }, [mutation]);

  // SUCCESS
  if (mutation.isSuccess) {
    return <SuccessPanel result={mutation.data} onReset={handleReset} />;
  }

  // ERROR
  if (mutation.isError) {
    const message =
      mutation.error instanceof Error ? mutation.error.message : "An unexpected error occurred.";
    return <ErrorPanel message={message} onReset={handleReset} />;
  }

  // UPLOADING / PROCESSING
  if (mutation.isPending && pendingFile) {
    return <UploadProgress filename={pendingFile.name} percent={uploadPercent} />;
  }

  // FILE SELECTED (preview before upload)
  if (pendingFile) {
    return (
      <FilePreview
        file={pendingFile}
        onClear={handleReset}
        onUpload={handleUpload}
        validationError={validationError}
      />
    );
  }

  // IDLE
  return <DropZone onFile={handleFileChosen} />;
}
