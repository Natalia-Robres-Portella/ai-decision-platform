## What does this PR do?

<!--
One paragraph. What changed and why?
Example: "Adds a /api/v1/documents/list endpoint so the frontend can show
which PDFs have been ingested. Previously there was no way to query this
without hitting the DB directly."
-->



## How to test?

<!--
Step-by-step instructions a reviewer can follow to verify this works.
Be specific — the reviewer shouldn't have to guess what to try.

Example:
1. Start the backend: cd backend && uvicorn app.main:app --port 8002 --reload
2. Ingest a PDF: curl -X POST http://localhost:8002/api/v1/documents/ingest -F "file=@tesla.pdf"
3. List documents: curl http://localhost:8002/api/v1/documents
4. Verify the ingested document appears in the response with status="ready"
-->



## Architectural decisions made

<!--
If you made a non-obvious design choice, explain it here.
This section is what makes PRs educational — it captures the WHY, not just the WHAT.

Examples worth documenting:
- "Used background task instead of await because SSE headers must be sent before the DB write"
- "Kept document_id as a string UUID rather than an integer PK to match Qdrant's point ID format"
- "Chose to filter in Python rather than Qdrant because the filter set is small and changes frequently"

If there were no interesting decisions, write "None — straightforward implementation."
-->



## Trade-offs considered

<!--
What did you NOT do, and why?
This is the most underrated part of a PR description.

Example:
- "Did not add pagination to /history — the limit=20 cap is sufficient for now.
  Adding cursor-based pagination before we have a use case would be premature."
- "Did not add a retry on OpenAI failures — a 503 to the client is clearer
  than a 20s timeout. We can add retries when we have metrics showing it's needed."
-->



## CI checklist (auto-verified)

- [ ] `ruff check` passes — no lint errors
- [ ] `ruff format --check` passes — code is formatted
- [ ] All 30 backend tests pass
- [ ] Coverage ≥ 80%
- [ ] TypeScript build succeeds
