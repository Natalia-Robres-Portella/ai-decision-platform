# AI Decision Intelligence Platform

A RAG (Retrieval-Augmented Generation) system that ingests PDF documents and answers questions with grounded, cited responses. Built with FastAPI, React, Qdrant, and PostgreSQL.

> For the product story, architecture decisions, and interview preparation, see **[PRODUCT.md](PRODUCT.md)**.

---

## Quick Start

```bash
# 1. Start infrastructure (Postgres + Qdrant)
cp .env.example .env          # fill in OPENAI_API_KEY
docker compose up -d

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3001 |
| API docs | http://localhost:8002/docs |
| Health check | http://localhost:8002/api/v1/health |
| Qdrant dashboard | http://localhost:6333/dashboard |

> **Port note:** Backend on 8002, Postgres on 5434, frontend on 3001 — all non-default to avoid conflicts with other local projects.

---

## What's Built

### Backend — FastAPI + Python 3.11

| Route | Description |
|-------|-------------|
| `POST /api/v1/documents/ingest` | Upload a PDF → chunk → embed → store in Qdrant |
| `GET  /api/v1/documents` | List all ingested documents with status |
| `POST /api/v1/ask` | Non-streaming question answering |
| `POST /api/v1/ask/stream` | SSE streaming — tokens arrive in real time |
| `GET  /api/v1/history` | Past question/answer pairs from PostgreSQL |
| `POST /api/v1/eval/run` | Run the full evaluation suite (10 questions, 4 metrics) |
| `GET  /api/v1/health` | Liveness + dependency status |

**RAG pipeline:**
1. `pypdf` extracts text page by page (preserving page numbers for citations)
2. `tiktoken` (cl100k_base) chunks text into 512-token windows with 50-token overlap
3. OpenAI `text-embedding-3-small` produces 1536-dimension vectors
4. Vectors upserted to Qdrant collection (`cosine` distance)
5. At query time: embed question → ANN search (top-5, score threshold 0.45) → build context block → `gpt-4o-mini` (temp=0.2) → stream tokens via SSE

### Frontend — React 18 + TypeScript + Tailwind

| Page | Route | Description |
|------|-------|-------------|
| Documents | `/ingest` | Drag-and-drop upload, real-time progress bar, document table with status badges |
| Chat | `/chat` | Conversation interface, document filter, streaming responses, collapsible citations |
| Evaluation | `/eval` | Evaluation dashboard with summary cards and per-question metric table |

**State management:**
- **React Query** — server state (documents, history). Auto-polls while any document is `processing`.
- **Zustand** — client state (selected document IDs for scoped queries, chat message history).

### Evaluation Framework

Automated quality measurement using GPT-4o-mini as a judge:

| Metric | What it measures | Score |
|--------|-----------------|-------|
| **Faithfulness** | % of answer sentences grounded in retrieved context (hallucination detector) | 0–100% |
| **Relevance** | Quality of retrieved chunks for the question | 1–5 |
| **Completeness** | Whether the answer addresses all aspects of the question | 1–5 |
| **Latency** | Retrieval ms + total ms | milliseconds |

```bash
cd backend
make eval         # runs 10 test questions, prints coloured table, saves JSON report
```

---

## Project Structure

```
ai-decision-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                  # App factory, lifespan (DB + Qdrant init)
│   │   ├── config.py                # pydantic-settings — typed env vars
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── ingestion.py     # POST /documents/ingest, GET /documents
│   │   │   │   ├── qa.py            # POST /ask, POST /ask/stream
│   │   │   │   ├── retrieval.py     # POST /retrieve (debug endpoint)
│   │   │   │   ├── eval.py          # POST /eval/run
│   │   │   │   └── health.py        # GET /health
│   │   │   └── dependencies.py      # FastAPI DI: get_db()
│   │   ├── services/
│   │   │   ├── ingestion_service.py # load_pdf → chunk → embed_and_store
│   │   │   ├── retrieval_service.py # embed_query → Qdrant ANN search
│   │   │   └── qa_service.py        # retrieve → prompt → GPT → SSE stream
│   │   ├── evaluation/
│   │   │   └── evaluator.py         # faithfulness / relevance / completeness
│   │   ├── repositories/
│   │   │   └── history_repository.py
│   │   ├── db/
│   │   │   ├── models.py            # SQLAlchemy ORM models
│   │   │   ├── base.py
│   │   │   └── session.py           # AsyncSessionLocal, engine
│   │   └── schemas/                 # Pydantic request/response models
│   ├── evaluation/
│   │   ├── test_dataset.json        # 10 test questions (3 documents)
│   │   └── run_eval.py              # CLI runner (calls POST /eval/run)
│   ├── tests/
│   │   ├── unit/                    # pytest + aiosqlite (no real DB needed)
│   │   └── integration/
│   ├── Makefile
│   └── pyproject.toml               # ruff config (line-length=100, E/F/I)
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── chat/
│       │   │   ├── MessageList.tsx  # Conversation bubbles + SSE state
│       │   │   ├── MessageInput.tsx # Auto-growing textarea, Enter=send
│       │   │   └── DocumentFilter.tsx  # Collapsible scope selector
│       │   ├── DocumentUploader.tsx # 6-state upload machine
│       │   ├── DocumentList.tsx     # Table with polling + skeleton rows
│       │   ├── ConfidenceBadge.tsx
│       │   └── SourceCard.tsx
│       ├── hooks/
│       │   └── useStreamAnswer.ts   # fetch + ReadableStream SSE consumer
│       ├── pages/
│       │   ├── ChatPage.tsx
│       │   ├── IngestPage.tsx
│       │   └── EvalPage.tsx
│       ├── services/api.ts          # All HTTP calls via axios
│       ├── store/chatStore.ts       # Zustand: selectedDocIds + messages
│       └── types/index.ts           # TypeScript mirrors of Pydantic schemas
│
├── infra/
│   └── postgres/init.sql
├── docker-compose.yml               # Postgres + Qdrant (not the app)
└── .github/workflows/ci.yml         # 3 parallel jobs
```

---

## Architecture Decisions

### 1. Layered backend: routes → services → repositories

Each layer has one responsibility and knows nothing about the layers above it:

| Layer | Knows | Does not know |
|-------|-------|---------------|
| Routes | HTTP (parsing, status codes) | Business logic, SQL |
| Services | Business rules, orchestration | HTTP, database drivers |
| Repositories | SQL / Qdrant queries | Business logic, HTTP |

This makes each layer independently testable. Switching Qdrant to Pinecone means touching one file.

### 2. Async throughout

FastAPI is async-native. The backend uses `asyncpg` + `sqlalchemy[asyncio]` so database queries don't block the event loop. `asyncio.gather()` parallelises Qdrant and PostgreSQL calls where possible. In the evaluation route, questions run 3-at-a-time via a semaphore.

### 3. SSE streaming via `fetch` (not `EventSource`)

The browser's built-in `EventSource` only supports GET. The streaming endpoint is POST (question in the body). Solution: `fetch` + `response.body.getReader()` + manual SSE line parsing. 30 lines, no library, handles incomplete chunks via line buffering.

### 4. React Query for server state, Zustand for client state

React Query handles anything that lives on the server and can become stale (documents list, query history). It auto-polls while any document has `status === "processing"` and invalidates the cache after an upload. Zustand handles client-only UI state (which documents are selected for scoped queries, chat message history). Components subscribe to only the slices they need — no context re-render storms.

### 5. LLM-as-judge evaluation (no ground truth required)

Reference-based metrics (BLEU, ROUGE) require human-annotated reference answers — expensive to build. GPT-4o-mini judges semantic meaning directly. One call per metric per question, structured output via `response_format: json_object`. The faithfulness check splits the answer into sentences and verifies each one against the retrieved context — this is the hallucination detector.

### 6. Docker Compose for infrastructure only

Postgres and Qdrant run in Docker. The backend and frontend run natively (`uvicorn`, `vite`). This gives hot-reload without rebuilding images, readable tracebacks in the terminal, and faster iteration. The Dockerfiles exist for production deployment.

---

## Running Tests

```bash
# Backend
cd backend
make test           # all tests
make test-unit      # fast unit tests only
make test-cov       # tests + coverage (must stay ≥ 80%)
make eval           # RAG evaluation suite (backend must be running)

# Backend linting
ruff check app/ tests/
ruff format app/ tests/

# Frontend
cd frontend
npm test            # vitest
npm run build       # tsc + vite build (catches type errors)
npm run lint        # ESLint
```

---

## CI Pipeline

Three parallel GitHub Actions jobs run on every push and PR:

| Job | Checks |
|-----|--------|
| **lint** | `ruff check` + `ruff format --check` (Python), ESLint + Prettier (TypeScript) |
| **test-backend** | pytest with Postgres + Qdrant services, coverage ≥ 80% |
| **test-frontend** | `vitest run`, `tsc && vite build` |

All three must be green to merge.

---

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Postgres (defaults match docker-compose.yml)
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
POSTGRES_USER=admin
POSTGRES_PASSWORD=password
POSTGRES_DB=ai_decision_db

# Qdrant (defaults match docker-compose.yml)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=documents
```

Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`. Everything else works with defaults if you use `docker compose up -d`.
