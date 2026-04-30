// IngestPage is intentionally thin — it's a layout container that composes
// two self-contained components. Each component manages its own data fetching,
// mutations, and state. The page itself holds no state.
//
// This separation means:
// - DocumentUploader can be reused anywhere without IngestPage wrapping it
// - DocumentList can be embedded in other pages (e.g. a document picker modal)
// - Testing each in isolation is straightforward

import { DocumentList } from "@/components/DocumentList";
import { DocumentUploader } from "@/components/DocumentUploader";

export function IngestPage() {
  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-slate-900">Documents</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload PDF reports and financial documents for analysis.
        </p>
      </div>

      {/* Upload section */}
      <DocumentUploader />

      {/* Document list — auto-refreshes after upload via React Query cache */}
      <div className="mt-10">
        <DocumentList />
      </div>
    </div>
  );
}
