# AI Decision Intelligence Platform
### A RAG system that turns unstructured documents into cited, grounded answers

---

## The Problem

Knowledge workers at consulting firms spend 30–40% of their time searching through documents. Given a 200-page client report, finding the answer to "what was EBITDA margin in Q3?" means either reading the whole document or hoping Ctrl+F finds the right page. When the question spans multiple reports — "how do these two companies compare on working capital?" — manual search breaks down entirely.

LLMs can answer questions fluently, but they hallucinate. You cannot trust a financial answer that isn't traceable to a source. The gap is a system that retrieves the right information first, then generates an answer grounded only in that retrieved content — with citations to verify.

---

## The Solution

Upload any PDF. Ask questions in plain English. Get cited answers that trace back to specific pages.

The system explicitly refuses to answer from general knowledge. Every claim in the response is either sourced from the uploaded documents or flagged as unsupported. A confidence score (high / medium / low) reflects retrieval quality, not LLM confidence — a meaningful distinction.

**What it does:**
- Ingests PDF documents → chunks and indexes them semantically
- Retrieves the most relevant passages to any question
- Generates grounded answers via GPT-4o-mini, streaming token by token
- Shows which pages each claim comes from (relevance-scored citations)
- Measures its own quality via an automated evaluation suite

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (React)                          │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  Documents  │  │  Chat (SSE)      │  │  Evaluation       │  │
│  │  /ingest    │  │  /chat           │  │  /eval            │  │
│  └──────┬──────┘  └────────┬─────────┘  └─────────┬─────────┘  │
└─────────┼──────────────────┼───────────────────────┼────────────┘
          │                  │  HTTP / SSE            │
          ▼                  ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI  (port 8002)                          │
│                                                                  │
│  POST /documents/ingest          POST /ask/stream                │
│  GET  /documents                 GET  /history                   │
│  POST /eval/run                  GET  /health                    │
│                                                                  │
│  ┌───────────────────┐     ┌──────────────────────────────────┐ │
│  │  Ingestion        │     │  RAG Query Flow                  │ │
│  │                   │     │                                  │ │
│  │  pypdf parse      │     │  1. Embed question               │ │
│  │  → tiktoken chunk │     │     text-embedding-3-small       │ │
│  │    (512t / 50t ov)│     │  2. ANN search (cosine, top-5)  │ │
│  │  → OpenAI embed   │     │     score threshold: 0.45        │ │
│  │  → Qdrant upsert  │     │  3. Build context block          │ │
│  └─────────┬─────────┘     │  4. GPT-4o-mini (temp=0.2)      │ │
│            │               │     stream=True (SSE)            │ │
│            ▼               └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
          │                            │
          ▼                            ▼
┌──────────────────┐        ┌─────────────────────┐
│   Qdrant         │        │   PostgreSQL         │
│   (port 6333)    │        │   (port 5434)        │
│                  │        │                      │
│  Collection:     │        │  documents           │
│  "documents"     │        │  (id, filename,      │
│  1536-dim        │        │  status, chunks)     │
│  cosine dist.    │        │                      │
│  149 points      │        │  query_history       │
└──────────────────┘        │  (q, answer,         │
          │                 │  confidence, sources) │
          └──────────┐      └─────────────────────┘
                     ▼
          ┌─────────────────────┐
          │   OpenAI API        │
          │   text-embedding-   │
          │   3-small (ingest   │
          │   + query)          │
          │   gpt-4o-mini       │
          │   (generation)      │
          └─────────────────────┘
```

### Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.11 + FastAPI | Async-native, type-safe, auto-generates OpenAPI docs |
| Frontend | React 18 + TypeScript + Tailwind | Component model fits document-per-state UI |
| Vector store | Qdrant | Open-source, self-hosted, production-grade ANN |
| Relational DB | PostgreSQL 15 | Document metadata + query history |
| Embeddings | text-embedding-3-small | 1536 dimensions, strong multilingual performance, low cost |
| Generation | gpt-4o-mini | Sufficient quality at 10× lower cost than gpt-4o |
| Server state | React Query | Automatic polling, cache invalidation, loading states |
| Client state | Zustand | Shared document selection without Context re-render overhead |
| CI | GitHub Actions | 3 parallel jobs: lint / test-backend / test-frontend |

---

## Technical Decisions and Trade-offs

These are the choices where there was a real alternative and a real cost.

---

### 1. Synchronous ingestion vs async background task

**Chose:** Synchronous — the POST `/ingest` blocks until chunking and embedding are complete, then returns the chunk count immediately.

**The alternative:** Kick off a background Celery task, return a job ID, let the frontend poll for completion.

**Why synchronous:** The API contract is simpler. The caller knows immediately that the document is ready to query. For the file sizes in this use case (typical report PDFs, 1–50 MB), ingestion takes 5–20 seconds — acceptable for a single-user tool.

**The cost:** Large PDFs block the request. Under concurrent ingestion (multiple users uploading simultaneously), the event loop would queue up. For a production multi-tenant system, async + background tasks is the right call. I'd use FastAPI BackgroundTasks for short jobs and Celery for long-running ones.

---

### 2. Fixed-size token chunks (512t) vs semantic chunking

**Chose:** Sliding window over a flat token list — 512 tokens per chunk, 50-token overlap, using the exact tokenizer (`cl100k_base`) the embedding model uses.

**The alternative:** Semantic chunking — split at sentence or paragraph boundaries using an NLP library (spaCy, NLTK), producing variable-size chunks that preserve meaning better.

**Why fixed-size:** No additional dependencies. Predictable chunk count per document (useful for understanding storage costs). The 50-token overlap mitigates the worst-case boundary problem: a sentence that straddles a chunk boundary appears complete in at least one of the two adjacent chunks.

**The cost:** A 512-token window occasionally splits a key table or data point mid-way, producing chunks that reference "$4.2" without "billion" or the company name. For tabular financial data, a table-aware chunker would perform better.

---

### 3. Score threshold calibration (0.6 → 0.45)

**Chose:** A retrieval score threshold of 0.45 for `text-embedding-3-small` cosine similarity.

**Why 0.45, not the original 0.6:** After uploading actual documents (two CFD academic papers + one Tesla quarterly report) and testing real queries, legitimate questions like "What was Tesla's operating cash flow?" scored 0.44 — below the original 0.6 cutoff. The threshold was empirically too conservative for technical documents where query vocabulary doesn't match document vocabulary exactly.

**The real trade-off here is precision vs recall:**
- Higher threshold → fewer but more reliable answers; more "no relevant content" frustrations
- Lower threshold → more answers but occasionally off-topic chunks reach the LLM

**What I'd do with more time:** Per-collection thresholds. A financial report collection can tolerate a lower threshold (the vocabulary is consistent) while a mixed technical/narrative collection needs a higher one. A cross-encoder reranker after ANN retrieval would make this more robust than threshold tuning.

---

### 4. SSE streaming vs WebSockets

**Chose:** Server-Sent Events (`fetch` + `ReadableStream`) for real-time token delivery.

**Why SSE, not WebSockets:** SSE is unidirectional (server → client), which is all streaming text needs. It works over plain HTTP/1.1, requires no handshake negotiation, and reconnects automatically on network drops. WebSockets add bidirectional complexity for a use case where the client only ever reads.

**The constraint that forced `fetch` over `EventSource`:** The browser's native `EventSource` API only supports GET requests. Our streaming endpoint is POST (it needs the question in the body). The solution — `fetch` + `response.body.getReader()` + manual SSE line parsing — is 30 lines and works without any library.

**The cost:** With SSE, the client cannot send a cancellation signal mid-stream (the abort controller can close the connection, but the server keeps generating tokens until it checks the connection). For production, this wastes compute. A WebSocket or gRPC bidirectional stream would allow proper cancellation.

---

### 5. LLM-as-judge evaluation vs reference-based metrics

**Chose:** GPT-4o-mini as a judge for faithfulness, relevance, and completeness — no ground-truth answers required.

**The alternative:** Reference-based metrics (BLEU, ROUGE, BERTScore) that compare generated answers to human-written reference answers.

**Why LLM-as-judge:** Reference metrics require a human-annotated dataset — expensive to build for a new domain. LLM judges evaluate semantic meaning, not word overlap. They generalise to new questions without manual labelling. For a RAG system where we care "is this answer grounded in the source?" rather than "does it match a reference answer exactly?", LLM judgment is more relevant.

**The cost:** Using an LLM to evaluate an LLM creates a circular dependency. The judge could be systematically biased toward certain phrasings. It also costs money per eval run (~$0.05–$0.10 for 10 questions × 4 LLM calls each). For a production evaluation system, I'd supplement with human spot-checks and track metric drift over time.

---

### 6. In-session chat history vs persistent conversation

**Chose:** Conversation history stored in Zustand — persists while the tab is open, resets on page reload.

**Why not persist to the database:** Persistent chat history requires: (1) session management so users see their own history; (2) deciding which previous messages to include in the RAG context window (token budget); (3) schema migration for conversation threads. For a single-user MVP, this complexity delivers uncertain value. The current design keeps the session stateless, which makes the backend easy to scale horizontally.

**The cost:** Refreshing the page loses the conversation. For a real product, conversation persistence would be one of the first features to add — and the right design is a server-side conversation table with a client-side session token.

---

## Evaluation Framework

The system measures its own quality with three automated metrics, each computed by GPT-4o-mini-as-judge after every answer:

| Metric | What it measures | How |
|--------|-----------------|-----|
| **Faithfulness** | Hallucination rate | Splits the answer into sentences. Judges each sentence: "is this supported by the retrieved context?" Score = supported / total. |
| **Relevance** | Retrieval quality | Scores each retrieved chunk 1–5 for relevance to the question. Low scores mean the retrieval step is pulling semantically adjacent but wrong content. |
| **Completeness** | Answer coverage | Single 1–5 rating: "does the answer address all aspects of the question?" Includes a written explanation of what's missing. |
| **Latency** | Retrieval + total | Measured in milliseconds, split between embedding/ANN search and full generation time. |

The evaluation runs against a fixed 10-question test set spanning all three ingested document types. It can be triggered from the `/eval` dashboard or via `make eval` from the CLI.

**Why this matters for the interview story:** A system without evaluation is a demo. Evaluation makes it a product — you can now answer "is this system getting better or worse?" after any change to the chunking strategy, embedding model, or prompt.

---

## What I Would Change With More Time

In order of impact:

**1. Reranking layer after retrieval**
ANN search retrieves the top-K approximate neighbours. A cross-encoder reranker (like Cohere Rerank or a local `ms-marco` model) re-scores those K chunks with full attention to the query. Typical result: recall improves significantly without changing anything else. This would reduce threshold tuning from an art to a non-issue.

**2. Table and chart extraction**
pypdf extracts text but loses tabular structure. A PDF with a revenue table becomes unstructured text where row/column relationships are lost. For financial documents, this is critical. The right tool is a document parsing library (Unstructured.io, Azure Document Intelligence) that preserves table structure before chunking.

**3. Streaming evaluation progress**
The evaluation route takes 30–60 seconds. The frontend shows a spinner. Better UX: stream individual question results as they complete (Server-Sent Events, same pattern as chat). The first results appear in ~5 seconds while the rest load.

**4. Semantic chunking for mixed documents**
Replace the fixed sliding window with a hybrid: split at paragraph/section boundaries first, then apply token limits. This would prevent splitting a key sentence or data point mid-way — the most common source of low retrieval scores.

**5. Conversation memory with context compression**
Store conversation turns in the database with a session token. At query time, include the last N turns in the LLM context — but compress old turns (summarise rather than include verbatim) to stay within the token budget.

---

## Interview Answers

### "¿Qué problema resuelve esto?"

Consultants and analysts work with large document sets. Finding a specific data point in a 200-page report takes time; comparing across three reports is worse. The system gives you cited, source-verified answers in seconds instead of minutes — and it refuses to answer from general knowledge, which is the part that matters in professional settings where hallucinated numbers cause real damage.

### "¿Qué cambiarías si tuvieras más tiempo?"

The highest-leverage change is adding a reranker between ANN retrieval and the LLM. ANN search optimises for approximate nearest neighbours — it's fast but imprecise. A cross-encoder reranker re-scores the retrieved chunks with full attention to the query and dramatically improves precision without touching anything else. My second priority would be table-aware parsing, because the current text extraction loses the row/column relationships in financial tables — which are often exactly what people want to query.

### "¿Cuáles fueron los trade-offs más difíciles?"

Two stand out.

First, the threshold tuning. The retrieval score threshold determines whether the system answers or says "I don't know." Too high and legitimate questions get rejected; too low and weak chunks contaminate the context and produce hallucinated answers. It's a precision/recall curve with no globally correct answer — you calibrate it empirically on your documents. I discovered this the hard way: my initial threshold of 0.6 was rejecting valid answers on the actual test documents because technical vocabulary doesn't match as tightly as financial vocabulary.

Second, synchronous vs async ingestion. Synchronous is simpler — you upload, it returns, you're done. Async (background task + polling) is more scalable but adds a job queue, status polling, and a more complex client. I chose synchronous for the MVP because the file sizes are manageable and the simpler contract makes the system easier to reason about. In production with multiple concurrent users, that choice would need to change.

### "¿Cómo mediste que funcionaba bien?"

Three ways. First, unit tests with an 80% coverage requirement — these run in CI on every push. Second, an automated evaluation framework with three LLM-as-judge metrics that I built specifically for this: faithfulness (hallucination rate), relevance (retrieval quality), and completeness (answer coverage). Third, manual calibration — I uploaded my actual documents, asked representative questions, and observed where the system was failing. That's what revealed the threshold issue. The evaluation framework turns that manual debugging loop into something systematic: run `make eval`, get a report, see which questions degraded after a change.
