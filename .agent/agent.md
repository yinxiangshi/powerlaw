# AGENTS.md — PowerLaw Layer 1 Backend

> Build instructions for Claude Code. Read this whole file before writing any code.
> This repo is **Layer 1 only**: data ingestion + knowledge representation for a
> legal-AI "closing copilot". Pure backend. No frontend, no auth, no deployment.

---

## 1. What we are building

PowerLaw ingests a **data room of project-finance contracts**, parses them, extracts
the legal conditions, and represents everything as a **provenance-anchored deal graph**
that later layers query. This backend is the foundation the whole product builds on.

The reference deal is a real one (a solar project financing): borrower
`Innovative Solar 31, LLC`, agent `KeyBank`, lead document a `Financing Agreement`
whose **Article 3 "Conditions Precedent"** is effectively a closing checklist written by
lawyers. Our job in Layer 1 is to turn that (and the surrounding contracts) into
structured, sourced, uncertainty-aware facts.

**Input:** heterogeneous files (`.htm`, `.pdf`, `.docx`).
**Output:** an append-only event log whose projection is a queryable graph of
documents → segments → conditions / defined-terms / parties / dependencies, every node
anchored to the exact source text it came from.

---

## 2. Non-negotiable architecture principles

These are decisions already made. Do not redesign them; implement them.

1. **Event sourcing is the spine.** An append-only `events` table is the single source
   of truth. Every other table (`documents`, `segments`, `conditions`, …) is a
   **materialized view** rebuilt by folding events. **Never destructively `UPDATE` a
   domain fact** — append an event and re-project. A state change = `INSERT INTO events`
   **+** update the materialized row, in **one transaction**.

2. **Append-only is enforced at the DB**, not by convention:
   ```sql
   CREATE RULE no_update AS ON UPDATE TO events DO INSTEAD NOTHING;
   CREATE RULE no_delete AS ON DELETE TO events DO INSTEAD NOTHING;
   ```

3. **Every event carries `actor_type` ∈ {`system`, `model`, `human`}** and a "why":
   - `model` events carry a `derivation` JSONB (model name, prompt version, input spans,
     confidence).
   - `human` events carry a `rationale_id` (FK).
   - `system` (deterministic) events need neither.
   A model-produced fact and a human-verified fact must always be distinguishable.

4. **Provenance is the primary key of trust.** Every extracted node anchors to a
   `span = (document_id, version, char_start, char_end)`, carried on `segments`.
   A condition does not store `"§3.1(g)"` as a string — it points to the segment whose
   span is the literal clause text.

5. **Deterministic first, LLM second.** Structural parsing (the `ARTICLE N / Section N.N
   / (a)(b)` tree) is rule-based. The LLM only runs **per-segment**, grounded with that
   segment's text, returning Pydantic-validated structured output **plus the span relied
   on**. Never feed a whole contract to the LLM and ask for the graph.

6. **Uncertainty is first-class.** Every extracted node has `confidence` and
   `verification_status` ∈ {`unverified`, `lawyer_confirmed`, `lawyer_corrected`}.
   Low-confidence extractions route to a **review queue**, they are not silently accepted.

7. **One datastore: Postgres.** Nodes/edges as tables (traversed with **recursive CTEs**),
   the event log, **pgvector** for doc→project matching, **pg_trgm** for party-alias fuzzy
   matching. Do **not** add Neo4j, a vector DB, or Redis.

---

## 3. Tech stack

| Concern | Choice |
|---|---|
| Package mgmt / venv | **uv** (use `uv` for everything; `pyproject.toml`, no `requirements.txt`) |
| Web framework | **FastAPI** |
| ASGI server | **uvicorn** (`uvicorn[standard]`) |
| Validation / schemas | **Pydantic v2** + **pydantic-settings** |
| DB | **PostgreSQL 16** (extensions: `vector`, `pg_trgm`) |
| DB toolkit | **SQLAlchemy 2.0 (async)** + **asyncpg** driver |
| Migrations | **Alembic** |
| Vector type | **pgvector** (`pgvector` python package) |
| Background jobs | **Procrastinate** (Postgres-backed queue — keeps single datastore) |
| LLM | **anthropic** SDK (direct; **no LangChain / LlamaIndex**) |
| PDF parsing | **pymupdf** (`fitz`) |
| HTML parsing | **beautifulsoup4** + **lxml** (the SEC files are `.htm`) |
| DOCX parsing | **python-docx** |
| Logging | **structlog** (structured JSON logs) |
| Testing | **pytest** + **pytest-asyncio** + **httpx** (ASGI transport) |
| Lint / format | **ruff** (lint + format) |
| Type check | **pyright** (or mypy) |

Python **3.12+**. Everything async (async FastAPI handlers, async SQLAlchemy sessions,
async Anthropic client).

---

## 4. Data model

Implement as SQLAlchemy models + Alembic migration. DDL sketch (load-bearing fields shown;
add `id uuid default gen_random_uuid()`, timestamps as needed):

```sql
-- THE SPINE (source of truth, append-only)
events (
  id           bigserial primary key,
  project_id   uuid not null,
  ts           timestamptz not null default now(),
  actor_id     text not null,
  actor_type   text not null,          -- 'system' | 'model' | 'human'
  event_type   text not null,
  target_type  text,                   -- 'document'|'segment'|'condition'|'defined_term'|...
  target_id    uuid,
  payload      jsonb not null,         -- type-specific; {before, after} for changes
  derivation   jsonb,                  -- model acts: {model, prompt_version, input_spans, confidence}
  rationale_id uuid references rationales(id),
  caused_by    bigint references events(id)
);

rationales (
  id uuid primary key, text text not null, structured_tags jsonb,
  author text, created_at timestamptz default now(), is_privileged boolean default true
);

-- MATERIALIZED VIEWS (rebuilt from events; carry updated_by_event back-link)
documents (
  id uuid primary key, project_id uuid not null,
  type text,                 -- financing_agreement|epc|mipa|tax_equity_ecca|depositary|accounts|dev_services|articles|warrant|auditor_consent|unknown
  title text,                -- EXTRACTED from content, never the filename
  filename text, mime text, execution_date date, version int default 1,
  content_hash text not null, storage_path text,
  status text,               -- 'ingested'|'segmented'|'extracted'|'linked'|'error'
  confidence real, updated_by_event bigint
);

segments (                   -- structural backbone; the SPAN lives here
  id uuid primary key, document_id uuid not null,
  parent_id uuid, label text, heading text, text text,
  char_start int, char_end int, order_index int
);

conditions (                 -- the star (for Layer 2)
  id uuid primary key, segment_id uuid not null, project_id uuid not null,
  beneficiary_party uuid, obligor_party uuid,
  trigger text,              -- 'closing_date'|'each_credit_event'|'commercial_operation'|...
  requirement_text text,
  discretionary boolean default false,    -- "satisfactory to Administrative Agent"
  dating_rule text,         -- 'as_of_closing'|'recent_date'|'not_earlier_than_90d'|null
  status text default 'open',             -- 'open'|'satisfied'|'waived'|'post_closing'
  waivable_by text,
  confidence real, verification_status text default 'unverified',
  updated_by_event bigint
);

defined_terms ( id uuid primary key, document_id uuid, term text,
                defining_segment_id uuid, definition_kind text );  -- 'enumeration'|'descriptive'

parties       ( id uuid primary key, project_id uuid, canonical_name text, entity_type text );
party_aliases ( party_id uuid, alias text );                       -- pg_trgm index on alias

evidence_artifacts ( id uuid primary key, type text,
                     expected_by_condition uuid, fulfilled_by_document uuid, provider_party uuid );

llm_calls ( id uuid primary key, document_id uuid, segment_id uuid, purpose text,
            model text, prompt_version text, prompt text, response jsonb,
            input_tokens int, output_tokens int, latency_ms int, created_at timestamptz default now() );

-- EDGES
dependencies    ( from_condition uuid, to_condition uuid, source_segment uuid );  -- §3.1(f) certifies §3.1(e)
term_membership ( defined_term uuid, member_document uuid, member_party uuid, resolved boolean );
cross_refs      ( from_segment uuid, to_segment uuid, resolved boolean );
party_roles     ( party_id uuid, document_id uuid, role text );                   -- role is DOCUMENT-scoped

-- doc->project matching
document_embeddings ( document_id uuid, embedding vector(1024) );  -- adjust dim to model
```

`document_embeddings` / pgvector can be stubbed if embeddings aren't wired yet — leave the
table and a TODO. The graph is the priority.

---

## 5. Ingestion pipeline

Seven stages. Each emits events. Orchestrated as a Procrastinate job per document so steps
are **idempotent and retryable** (LLM steps fail; jobs must resume cleanly).

1. **Intake & normalize** — bytes → text, compute `content_hash` (dedup + tamper-evidence).
   Emit `DocumentIngested`.
2. **Document typing** — classify the doc from **title page / content, not filename**
   (LLM, low-temp). Emit `DocumentTyped`.
3. **Structural segmentation** — **deterministic** parse of `ARTICLE/Section/(a)(b)` into a
   segment tree with spans. Emit `DocumentSegmented`.
4. **Provision extraction** — per-segment LLM classification
   (`definition|condition|representation|covenant|event_of_default|rights|misc`); for
   conditions, extract the full `conditions` fields. Emit `ConditionExtracted` etc. (with
   confidence + span in `derivation`).
5. **Entity & term extraction** — parties, defined terms, dates, dollar amounts, internal
   cross-refs per segment.
6. **Linking** — resolve cross-refs → `cross_refs` + `dependencies`; resolve defined-term
   **bundle membership** (recursive) → `term_membership`; resolve inter-document references;
   attach expected evidence types → `evidence_artifacts`.
7. **Persist** — events appended throughout; materialized tables updated in the same txns.

**Validation gates:** Pydantic-validate every LLM output before persist; completeness checks
(every condition has a `beneficiary` + `trigger`; every defined-term reference resolves or is
flagged); confidence below `EXTRACTION_CONFIDENCE_THRESHOLD` → emit `ExtractionFlagged`
(routes to review queue) instead of accepting.

**The four hard problems** (implement in stage 6; these are the real work):
1. **Defined-term bundle resolution** — recursively resolve "Project Documents" etc. to
   concrete documents; **flag members referenced but missing** from the data room.
2. **Cross-reference resolution** — "as provided in Section 3.1(f)" → a `dependencies` edge;
   unresolved refs are flagged, not swallowed.
3. **Inter-document entity resolution** — "the Tax Equity ECCA" inside one doc → the actual
   ECCA document node.
4. **Party/role normalization** — alias table + `pg_trgm`; roles attached per document.

---

## 6. API surface

All JSON, all async. Prefix `/api/v1`.

**Projects**
- `POST /projects` — create. body: `{name, aliases[]}`
- `GET /projects` — list with health counters
- `GET /projects/{id}` — detail + counters (docs ingested, conditions extracted,
  % satisfied, # awaiting review)

**Documents / upload / processing**
- `POST /projects/{id}/documents` — **multipart upload** (one or many files). Stores file,
  computes hash, emits `DocumentIngested`, **enqueues processing job**, returns
  `{document_id, job_id}` per file.
- `GET /documents/{id}` — metadata + `status`
- `GET /documents/{id}/segments` — segment tree
- `GET /documents/{id}/text` — normalized text (for provenance display)
- `POST /documents/{id}/reprocess` — re-enqueue pipeline
- `GET /jobs/{id}` — job status (queued/running/done/error)

**Graph reads**
- `GET /projects/{id}/conditions` — extracted conditions (filter by `trigger`, `status`,
  `verification_status`); each includes provenance (segment id, label, span, doc).
- `GET /projects/{id}/defined-terms` — terms + resolved/missing bundle members
- `GET /projects/{id}/parties` — parties + roles
- `GET /conditions/{id}` — full detail incl. dependencies + source clause text

**Human verification (the L1↔L3 seam — needed to demonstrate the event loop)**
- `POST /conditions/{id}/confirm` — emit `ConditionConfirmed` (human)
- `POST /conditions/{id}/correct` — body includes `{field, new_value, rationale}`; emit
  `ConditionCorrected` (human, with rationale)
- `GET /projects/{id}/review-queue` — flagged low-confidence / unresolved items

**Audit (Layer 4 reads the same log)**
- `GET /projects/{id}/events` — reverse-chronological; filter by `actor_type`, `event_type`,
  `document_id`, `after`, `before`. Each event includes its "why" (derivation or rationale)
  and `caused_by`.
- `GET /projects/{id}/state?as_of=<ts>` — time-travel: project state as of a timestamp
  (replay/fold events up to `ts`).

> Note: generating the actual closing **checklist** is Layer 2. Layer 1 exposes
> `conditions` and the graph; a `GET /projects/{id}/checklist` stub may return the
> dependency-sorted conditions, but full checklist rendering is out of scope here.

---

## 7. Project structure

```
powerlaw-backend/
├── pyproject.toml
├── .env.example
├── AGENTS.md
├── README.md
├── docker-compose.yml            # postgres 16 + pgvector + pg_trgm
├── alembic.ini
├── migrations/
└── src/powerlaw/
    ├── main.py                   # FastAPI app, router include, lifespan
    ├── config.py                 # pydantic-settings Settings
    ├── db.py                     # async engine, session factory
    ├── logging.py                # structlog setup
    ├── worker.py                 # Procrastinate app + job definitions
    ├── events/
    │   ├── types.py              # EventType enum + per-type payload models (Pydantic)
    │   ├── store.py              # append_event() — the ONLY way to write truth
    │   └── projections.py        # fold events -> materialized tables; as_of()
    ├── models/tables.py          # SQLAlchemy table defs
    ├── schemas/
    │   ├── extraction.py         # Condition, DefinedTerm, Party… (LLM structured output)
    │   └── api.py                # request/response models
    ├── ingestion/
    │   ├── intake.py  typing.py  segmentation.py
    │   ├── extraction.py  entities.py  linking.py
    │   └── pipeline.py           # orchestrates the 7 stages (the job body)
    ├── parsers/  pdf.py  html.py  docx.py
    ├── llm/
    │   ├── client.py             # async Anthropic wrapper — logs EVERY call to llm_calls
    │   └── prompts.py            # versioned prompts (prompt_version string)
    ├── repositories/             # data access; recursive CTEs live here
    └── api/
        ├── routes_projects.py  routes_documents.py
        ├── routes_conditions.py routes_events.py routes_review.py
└── tests/
```

---

## 8. Conventions

- **All writes to domain truth go through `events.store.append_event()`** which, in one
  transaction, inserts the event and updates the materialized projection. No route or
  service writes a `conditions` row directly.
- **Every LLM call goes through `llm/client.py`** and is logged to `llm_calls` (prompt,
  response, model, prompt_version, tokens, latency). Extraction quality is the product —
  we want the eval trail from day one.
- **Prompts are versioned** (`prompt_version` string in `prompts.py`); the version goes into
  the event `derivation` so any extraction is reproducible/explainable.
- Pydantic v2 everywhere; LLM structured output uses Anthropic **tool use** mapped to
  Pydantic models; validate before persist.
- Full type hints; `ruff` clean; `pyright` clean.
- Async SQLAlchemy sessions via dependency injection in FastAPI.
- Config only via `pydantic-settings` reading `.env`; never hardcode secrets or model names.
- Errors: domain errors → structured HTTP responses; pipeline errors → `status='error'` on
  the document + an error event, never a silent swallow.

---

## 9. MVP scope cut (do this, not more)

- **All documents:** typed + structurally segmented + party-tagged. (Cheap, mostly
  deterministic; enough for later doc→project matching.)
- **Deep extraction only on:** the Financing Agreement's **Article 3** conditions + the
  defined-term bundles those conditions reference (Project Documents, Financing Documents,
  Tax Equity Documents) + evidence-type tagging.
- That is exactly enough graph to drive the §3.1 + §3.2 checklist later. Everything else is
  a future pass.

**Out of scope for Layer 1:** auth, multi-tenant access control, deployment/hosting,
the frontend, the Word/Chrome copilot, hash-chaining of events, snapshots, the
checklist *rendering* (Layer 2), the dashboard (Layer 4). Leave clean seams (the events
table, the `as_of` projection, `is_privileged` on rationales) but don't build them.

---

## 10. Commands

```bash
# setup
uv sync
docker compose up -d              # postgres with pgvector + pg_trgm
uv run alembic upgrade head

# run
uv run uvicorn powerlaw.main:app --reload
uv run procrastinate --app=powerlaw.worker.app worker   # background worker

# quality
uv run ruff check . && uv run ruff format .
uv run pyright
uv run pytest

# new migration
uv run alembic revision --autogenerate -m "msg"
```

---

## 11. Build order (suggested)

1. Scaffold (`uv init`, deps, config, db, structlog, docker-compose, alembic baseline).
2. **Events core**: `events` table + append-only rule, `append_event()`, `rationales`,
   `llm_calls`. Prove: append an event, read it back.
3. Materialized tables + projections + the `as_of` fold.
4. Parsers (`html`/`pdf`/`docx`) → normalized text + hash. `POST documents` upload +
   Procrastinate job skeleton. Emit `DocumentIngested`.
5. **Deterministic segmentation** → segment tree with spans. Emit `DocumentSegmented`.
6. LLM client (+ `llm_calls` logging) → document typing → per-segment provision/condition
   extraction with confidence + span. Review-queue flagging.
7. Linking: cross-refs, dependencies, **bundle resolution**, parties/roles.
8. Read APIs: conditions, events (with filters), review-queue, `as_of`. Verification
   endpoints (confirm/correct → events).
9. Tests across the pipeline on the reference Financing Agreement; assert §3.1 conditions
   extract with provenance and dependencies (e.g. 3.1(f) → 3.1(e)).

**Definition of done for Layer 1:** upload the data room → pipeline runs → `GET conditions`
returns Article 3 CPs each with a working provenance link and dependency edges →
`GET events` reconstructs who/what/why → a `correct` call appends an event and re-projects
the condition. One log, queryable graph, full audit.
