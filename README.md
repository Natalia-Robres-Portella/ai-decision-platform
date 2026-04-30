# AI Decision Intelligence Platform

A system that helps users make strategic business decisions by analyzing documents, news, and financial reports using RAG + LLM.

---

## Quick Start

```bash
# 1. Start infrastructure (Postgres + Qdrant)
cp .env.example .env
docker compose up -d

# 2. Run the backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload

# 3. Run the frontend
cd frontend
npm install
npm run dev
```

Health check: http://localhost:8002/api/v1/health  
API docs: http://localhost:8002/docs  
Frontend: http://localhost:3000

> **Note on ports**: port 8000 is used by other Docker containers on this machine. We use 8002 for the backend and 5434 for PostgreSQL (5432 and 5433 are also taken).

---

## Project Structure

```
ai-decision-platform/
├── backend/            # Python + FastAPI
│   ├── app/
│   │   ├── main.py         # App factory + middleware
│   │   ├── config.py       # Typed settings from env vars
│   │   ├── api/
│   │   │   ├── routes/     # HTTP handlers only
│   │   │   └── dependencies.py  # FastAPI DI providers
│   │   ├── services/       # Business logic
│   │   ├── repositories/   # Data access (DB + vector store)
│   │   ├── models/         # Pydantic schemas (request/response)
│   │   └── db/             # SQLAlchemy engine + session factory
│   └── tests/
├── frontend/           # React + TypeScript + Tailwind
│   └── src/
│       ├── components/     # Reusable UI components
│       ├── pages/          # Route-level page components
│       ├── services/       # API call functions
│       └── types/          # Shared TypeScript interfaces
├── infra/
│   └── postgres/
│       └── init.sql        # DB bootstrap (extensions, not tables)
└── docker-compose.yml  # Local dev infrastructure
```

---

## Architecture Decisions

### 1. Monorepo layout (`/backend`, `/frontend`, `/infra`)

Keeping everything in one repo makes it easy to:
- Run the full system with a single `docker compose up`
- Share type contracts between layers (in the future, via OpenAPI codegen)
- Coordinate changes that span backend + frontend in one PR

The tradeoff: as the project grows, a monorepo requires discipline to keep concerns separated. Tools like `nx` or `turborepo` help at scale, but we don't need them yet.

### 2. Layered backend architecture: routes → services → repositories

Each layer has exactly one responsibility:

| Layer | Knows about | Doesn't know about |
|-------|-------------|-------------------|
| **Routes** | HTTP (request parsing, status codes, auth headers) | Database, business rules |
| **Services** | Business logic, orchestration, domain rules | HTTP, SQL |
| **Repositories** | SQL / vector store queries | Business logic, HTTP |

**Why this matters**: you can test each layer in isolation. A service test doesn't need an HTTP client. A route test doesn't need a real database. When you switch from Qdrant to Pinecone, only the repository changes.

### 3. `pydantic-settings` for configuration

`app/config.py` defines a `Settings` class that reads from environment variables (and a `.env` file locally). Benefits:
- **Type safety**: `POSTGRES_PORT` is an `int`, not a string
- **Validation at startup**: the app crashes early with a clear error if a required env var is missing
- **One source of truth**: no scattered `os.getenv()` calls

The `settings` singleton is imported wherever needed. This is simpler than a dependency-injected config for most projects.

### 4. Async SQLAlchemy with `asyncpg`

FastAPI is async-first. Using `asyncpg` (the async PostgreSQL driver) with `sqlalchemy[asyncio]` means DB queries don't block the event loop — the server can handle other requests while waiting for the database. The sync alternative (`psycopg2`) would bottleneck under concurrent load.

`expire_on_commit=False` is set on the session factory to avoid SQLAlchemy trying to lazily reload attributes after a commit, which would fail in an async context.

### 5. DB session as a FastAPI dependency

`get_db()` in `api/dependencies.py` is an async generator that:
1. Opens a session
2. Yields it to the route handler
3. Commits on success, rolls back on exception

This means every request gets its own isolated transaction automatically. Routes and services never call `session.commit()` directly — the dependency manages the lifecycle.

### 6. Health check design

The `/api/v1/health` endpoint checks each infrastructure dependency (Postgres, Qdrant) independently and reports a `status` per component:
- `"ok"` — all components healthy
- `"degraded"` — some components failing, others working
- `"error"` — everything down

**Why**: a binary healthy/unhealthy check doesn't give enough signal for debugging. With `"degraded"`, a load balancer can still route traffic while an engineer investigates a non-critical component.

### 7. Vite dev proxy for the frontend

In `vite.config.ts`, requests to `/api/*` are proxied to `http://localhost:8000`. This means:
- The browser sees everything on `http://localhost:3000` — no CORS issues during development
- The production build just needs an nginx reverse proxy doing the same routing
- No hardcoded backend URLs in frontend code

### 8. Docker Compose for local infrastructure only

`docker-compose.yml` runs Postgres and Qdrant, but **not** the backend or frontend. The app processes run natively (`uvicorn`, `vite`) so you get:
- Hot reload without rebuilding Docker images
- Readable tracebacks directly in the terminal
- Faster iteration during development

The Dockerfiles exist for production deployment, not local dev.

### 9. Why Qdrant as the vector store?

| Option | Hosting | Notes |
|--------|---------|-------|
| **Qdrant** | Self-hosted (Docker) | Open source, no API key needed locally, fast |
| Pinecone | Managed SaaS | Easier ops, but requires account + costs money |
| pgvector | PostgreSQL extension | One less service, but less feature-rich |

Qdrant is the right choice for local learning: zero cost, full control, and it's a production-grade system used in real applications.

---

## What's Next

| Step | What we'll build |
|------|-----------------|
| **Step 2** | SQLAlchemy models + Alembic migrations |
| **Step 3** | Document upload endpoint (PDF, text) |
| **Step 4** | LlamaIndex RAG pipeline + OpenAI embeddings |
| **Step 5** | Qdrant vector indexing + similarity search |
| **Step 6** | Query endpoint with LLM-generated answers |
| **Step 7** | Frontend: upload UI + chat interface |

---

## Running Tests

```bash
# Backend
cd backend
make test          # run all tests
make test-unit     # unit tests only (fast)
make test-cov      # tests + coverage report (must stay ≥ 80%)

# Lint before committing
ruff check backend/app backend/tests   # lint
ruff format backend/                   # auto-format

# Frontend
cd frontend
npm test           # vitest (watch mode)
npm run lint       # ESLint
npm run format     # auto-format with Prettier
npm run build      # TypeScript + Vite build (catches type errors)
```

---

## CI Pipeline

Every pull request and push to `main` runs three parallel GitHub Actions jobs:

| Job | What it checks |
|-----|----------------|
| **lint** | `ruff check` + `ruff format --check` (Python), ESLint + Prettier (TypeScript) |
| **test-backend** | 30 pytest tests, ≥80% coverage, uploaded to Codecov |
| **test-frontend** | `vitest run`, `tsc && vite build` |

All three must be green before a PR can be merged.

### One-time GitHub setup (do this when you create the repo)

**1. Add GitHub Secrets** (Settings → Secrets and variables → Actions → New repository secret):

| Secret name | Value |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI key (tests mock it, but good practice to have it) |
| `CODECOV_TOKEN` | From [codecov.io](https://codecov.io) after connecting the repo |

**2. Enable branch protection on `main`** (Settings → Branches → Add rule):

```
Branch name pattern: main

✅ Require a pull request before merging
   ✅ Require approvals: 1
   ✅ Dismiss stale pull request approvals when new commits are pushed

✅ Require status checks to pass before merging
   ✅ Require branches to be up to date before merging
   Status checks required:
     - Lint (Python + TypeScript)
     - Backend tests (Python 3.11)
     - Frontend tests + build (Node 20)

✅ Do not allow bypassing the above settings
```

With these rules:
- No one (including you) can push directly to `main`
- PRs can only merge when all three CI jobs are green
- Stale approvals are dismissed when you push new commits to a PR

**3. Connect Codecov** (optional but recommended):
1. Go to [codecov.io](https://codecov.io) and sign in with GitHub
2. Add your repository
3. Copy the upload token to the `CODECOV_TOKEN` secret above
4. Codecov will comment on PRs showing coverage changes per-line

---

## First PR workflow

Practice the full team workflow on your first feature:

```bash
# 1. Create a feature branch (never commit directly to main)
git checkout -b feature/add-document-list-endpoint

# 2. Make your change, then run checks locally
cd backend
ruff check app/ tests/    # must pass
ruff format app/ tests/   # auto-fix formatting
make test                 # must be 30/30

# 3. Commit and push
git add -p                # stage hunks interactively (avoid accidental secrets)
git commit -m "feat: add GET /documents endpoint to list ingested PDFs"
git push -u origin feature/add-document-list-endpoint

# 4. Open a PR on GitHub
# The PR template auto-fills — answer the four sections
# GitHub Actions kicks off automatically

# 5. Watch CI run at: github.com/<you>/ai-decision-platform/actions
# Green on all three jobs → ready for review → merge
```
