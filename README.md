# PowerLaw

PowerLaw is a project-finance document dashboard. It ingests deal files, extracts
parties, defined terms, checklist conditions, dependencies, and evidence expectations,
then exposes the result as a provenance-backed project workspace with files,
conditions, review flags, terms, graph, and audit history.

The repo contains:

- FastAPI backend under `src/powerlaw`
- PostgreSQL 16 database via Docker Compose
- append-only audit/event log with projection tables
- deterministic parsers plus optional OpenAI review calls
- Next.js frontend under `frontend`
- Microsoft Word copilot add-in under `plugin`
- fixture data under `data/exhibits`

## Setup Instructions

These steps assume a fresh clone and no prior local context.

### 1. Install prerequisites

Install:

- Docker Desktop, or another Docker Compose-compatible runtime
- `uv` for Python dependency management
- Node.js 20+ and `npm`

### 2. Clone and enter the repo

```bash
git clone <repo-url>
cd powerlaw
```

### 3. Create local environment config

```bash
cp .env.example .env
```

The default `.env.example` points the app at the bundled local Postgres service:

```text
DATABASE_URL=postgresql+asyncpg://powerlaw:powerlaw@localhost:5434/powerlaw
STORAGE_DIR=storage
PROCESS_UPLOADS_INLINE=true
OPENAI_MODEL=gpt-5.4
```

LLM calls are optional. To enable them, set `OPENAI_API_KEY` in `.env`. Without
that key, ingestion and checklist extraction still work through deterministic parsing.

### 4. Start Postgres

```bash
docker compose up -d
```

The database is exposed on local port `5434` to avoid collisions with an existing
Postgres on `5432`.

### 5. Install backend dependencies and run migrations

```bash
uv sync
uv run alembic upgrade head
```

### 6. Optional: seed fixture data

The test data room lives in `data/exhibits`.

```bash
uv run python -m powerlaw.seed --data-dir data/exhibits
```

You can also create a project and upload files through the UI instead of seeding.

### 7. Start the API

Run the API on `8001`, which matches the frontend default:

```bash
uv run uvicorn powerlaw.main:app --host 127.0.0.1 --port 8001
```

Useful URLs:

- API docs: `http://127.0.0.1:8001/docs`
- API base: `http://127.0.0.1:8001/api/v1`

### 8. Install and start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3001
```

Open:

```text
http://127.0.0.1:3001
```

If you run the API somewhere other than `http://127.0.0.1:8001/api/v1`, set this
in `frontend/.env.local` before starting Next.js:

```text
POWERLAW_API_BASE_URL=http://127.0.0.1:8001/api/v1
NEXT_PUBLIC_POWERLAW_API_BASE_URL=http://127.0.0.1:8001/api/v1
```

### 9. Install and start the Word copilot add-in

The Word copilot lives in `plugin`. It is an Office.js task pane add-in that
talks to the local PowerLaw API through the plugin dev server.

Keep the backend running on `http://127.0.0.1:8001`, then in another terminal:

```bash
cd plugin
npm install
```

Word requires add-ins to load over HTTPS. The dev server automatically uses
HTTPS when it finds local certificate files at:

```text
plugin/certs/localhost.pem
plugin/certs/localhost-key.pem
```

Recommended local certificate setup with `mkcert`:

```bash
cd plugin
mkdir -p certs
mkcert -install
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1
```

Start the add-in server:

```bash
npm run dev
```

Expected URLs:

```text
Task pane: https://localhost:3101/taskpane.html
Manifest:  https://localhost:3101/manifest.xml
API proxy: /api/* -> http://127.0.0.1:8001
```

Use port `3101` for Word. The manifest currently hardcodes
`https://localhost:3101`; if you run the server on another port, update
`plugin/manifest.xml` before sideloading.

### 10. Sideload the Word add-in on macOS

Create Word's local sideload folder and copy the manifest:

```bash
mkdir -p "$HOME/Library/Containers/com.microsoft.Word/Data/Documents/wef"
cp plugin/manifest.xml "$HOME/Library/Containers/com.microsoft.Word/Data/Documents/wef/powerlaw-manifest.xml"
```

Then:

1. Quit and reopen Microsoft Word.
2. Open a `.docx` that belongs to a seeded or uploaded PowerLaw project.
3. In Word, open `Insert > Add-ins > My Add-ins` if the add-in is not already
   visible.
4. Select `PowerLaw Copilot`.
5. Use the `PowerLaw` group on the Home ribbon, then click `Open Copilot`.

If the add-in does not appear, confirm the plugin server is still running at
`https://localhost:3101/taskpane.html`, the certificate is trusted, and the
manifest was copied into the `wef` folder above.

### 11. Use the Word copilot

The intended MVP workflow is:

1. Open the PowerLaw Copilot task pane in Word.
2. Click `Recognize matter`.
3. Confirm the suggested PowerLaw project or choose the correct tag.
4. Optionally select text in the document to use as drafting context.
5. Choose `Clause`, `Section`, or another content kind.
6. Write drafting instructions and click `Generate`.
7. Click `Insert tracked text` to insert the generated language into Word.
8. Edit or delete generated text directly in Word.
9. Review the rationale queue in the task pane.
10. Add a reason and categories for each queued change.
11. Click `Sync rationale` or `Sync all rationales`.

Generated clauses and sections are wrapped in Word content controls. Each
insertion gets its own tracking id, so the same generated draft can be inserted
in multiple places. The add-in also watches normal document-body edits and queues
them for rationale capture.

Important MVP limitation: Office.js cannot reliably intercept every native Word
Save or Close action across desktop and web clients. For now, PowerLaw enforces
rationales before syncing edit observations back to the backend and before using
those edits as future drafting memory.

## Common Commands

Backend checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev pyright
uv run --extra dev pytest
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Word add-in checks:

```bash
cd plugin
npm run check
```

## Key Design Decisions

1. **Append-only event log first.**
   Every meaningful system or user action is recorded as an event, then projected
   into read models such as documents, conditions, parties, dependencies, and audit
   views. This makes provenance, review history, and lawyer-facing audit trails part
   of the core model rather than a later reporting layer.

2. **Provenance-anchored extraction.**
   Conditions, terms, cross references, and graph links point back to source
   document spans. Legal review needs to answer "where did this come from?" quickly,
   so source context is carried through the API and frontend instead of showing
   extracted text as detached data.

3. **Deterministic parsing with optional LLM review.**
   The parser extracts structural candidates first. If `OPENAI_API_KEY` is present,
   the OpenAI client can review/refine checklist conditions and stores the LLM call
   and reasoning. This keeps the system useful without an LLM key while still giving
   an auditable path for model-assisted extraction.

## What I Would Do Differently With More Time

- Move long-running ingestion and checklist generation to a durable worker queue
  instead of relying primarily on inline processing during upload.
- Invest in broader end-to-end tests and richer extraction evaluation fixtures,
  especially around non-fixture agreements, failed uploads, and LLM edge cases.

## Architecture

See [arch.md](arch.md).
