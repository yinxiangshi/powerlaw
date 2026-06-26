# System Architecture

PowerLaw is split into a FastAPI backend, a PostgreSQL event/projection store, a
Next.js frontend, local file storage, and an optional OpenAI review layer.

```mermaid
flowchart LR
    U["User / law-firm reviewer"]
    FE["Next.js frontend<br/>project dashboard"]
    API["FastAPI API<br/>/api/v1"]
    FS["Local file storage<br/>storage/{project_id}"]
    DB[("PostgreSQL 16<br/>events + read models")]
    PIPE["Ingestion pipeline<br/>parse, segment, extract, link"]
    LLM["OpenAI Responses API<br/>optional condition review"]

    U --> FE
    FE --> API
    API --> FS
    API --> DB
    API --> PIPE
    PIPE --> FS
    PIPE --> DB
    PIPE -. "when OPENAI_API_KEY is set" .-> LLM
    LLM -. "reason + call log" .-> DB
    DB --> API
    API --> FE
```

## Component Roles

### Frontend

The frontend lives in `frontend` and uses Next.js, Tailwind CSS, shadcn-style UI
components, lucide icons, and D3 for the project graph.

Primary screens:

- Home: project overview, existing projects, create project
- Files: uploaded documents, upload form, per-document audit log
- Conditions: checklist table, status controls, frontend action controls, source dialogs
- Review: extraction and unresolved-link flags
- Terms: defined-term bundles and memberships
- Graph: whole-project graph across files, parties, terms, conditions, and dependencies
- Audit: full project event history

The frontend mostly calls the backend through server actions and typed helpers in
`frontend/src/lib/powerlaw-api.ts`.

### API

The FastAPI backend lives in `src/powerlaw/api` and is mounted under `/api/v1`.

Important route groups:

- `routes_projects.py`: create, list, soft-delete projects
- `routes_documents.py`: upload, list, reprocess, inspect documents
- `routes_conditions.py`: list/generate conditions, update status, log corrections
- `routes_events.py`: project and document audit history
- `routes_review.py`: review queue
- `routes_copilot.py`: drafting/copilot MVP endpoints

### Event Store And Projections

The `events` table is the source of truth for system history. Events are appended
through `powerlaw.events.store.append_event`, then projection logic in
`powerlaw.events.projections` updates query-friendly tables such as:

- `projects`
- `documents`
- `segments`
- `conditions`
- `parties`
- `defined_terms`
- `dependencies`
- `cross_references`
- `evidence_artifacts`
- `ingestion_jobs`

Human/dashboard actions include rationale records where appropriate, so the audit
view can show both what changed and why it changed.

### Ingestion Pipeline

Uploads are written to local storage, normalized, and processed by
`powerlaw.ingestion.pipeline`.

The high-level flow is:

1. Store uploaded file.
2. Append `DocumentIngested` and `JobCreated`.
3. Parse text from `.txt`, `.html`, `.docx`, or `.pdf`.
4. Classify document type and title.
5. Segment document structure with character spans.
6. Extract parties and defined terms.
7. Extract Article 3 checklist condition candidates.
8. Optionally review each candidate with OpenAI.
9. Link cross references, dependencies, defined-term memberships, and review flags.
10. Project all events into read models.

### Optional LLM Layer

The OpenAI client lives in `src/powerlaw/llm/client.py`. It uses the official OpenAI
library and defaults to `gpt-5.4`.

LLM calls only run when `OPENAI_API_KEY` is configured. Calls are stored in
`llm_calls`, and condition derivations keep the model, prompt version, input spans,
confidence, reason, and LLM call ID.

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as Next.js UI
    participant API as FastAPI
    participant Store as Event Store
    participant Pipeline
    participant LLM as OpenAI optional
    participant Read as Projection Tables

    User->>UI: Create project / upload files
    UI->>API: POST project or documents
    API->>Store: Append project/document/job events
    API->>Pipeline: Process upload inline
    Pipeline->>Store: Append typed, segmented, party, term events
    Pipeline->>Store: Append condition candidates
    alt OPENAI_API_KEY configured
        Pipeline->>LLM: Review condition candidate
        LLM-->>Pipeline: JSON review + reason
        Pipeline->>Store: Append model event + derivation
    end
    Store->>Read: Apply projections
    UI->>API: Fetch project workspace
    API->>Read: Query documents, conditions, terms, graph inputs
    API->>Store: Query audit events
    API-->>UI: Render workspace
```

## Storage And Runtime Defaults

- Database: `postgresql+asyncpg://powerlaw:powerlaw@localhost:5434/powerlaw`
- File storage: `storage/`
- API default local port used by the frontend: `8001`
- Frontend local port used in setup: `3001`
- Upload processing: inline by default with `PROCESS_UPLOADS_INLINE=true`
- LLM model: `gpt-5.4`

## Trust Boundary

The current app is an MVP and does not include authentication. It should be run as a
local development tool unless auth, tenant isolation, deployment hardening, and
production secrets management are added.
