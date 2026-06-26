# PowerLaw Word Copilot MVP

This folder is for the Microsoft Word add-in. The MVP assumption is:

- no authentication
- local development against the PowerLaw API on localhost
- Word task pane UI built with Office.js
- PowerLaw remains the source of truth for projects, documents, events, and rationales

## Product Goal

Meet the lawyer inside Word without turning drafting into a separate workflow.

The copilot should quietly recognize the matter/contract context, ask for confirmation only when confidence is low or ambiguous, track edits to generated content, and require the lawyer to explain why generated legal language was changed. Those rationales become future drafting memory.

## Ideal MVP Experience

1. The lawyer opens or edits a Word document.
2. The task pane shows a small project badge:
   - confirmed project and contract when known
   - suggested project when confidence is high
   - a short correction flow when confidence is low
3. If the lawyer inserts generated clauses or sections, PowerLaw wraps them in tracked Word content controls.
4. When a generated clause/section changes, the add-in detects the diff and queues it as "needs rationale."
5. The lawyer provides a short rationale before the edit is synced back to PowerLaw.
6. PowerLaw stores the edit, diff, and rationale as append-only events.
7. Future generation retrieves relevant prior rationales as drafting preferences.

## Architecture Sketch

```text
Word document
  |
  | Office.js task pane, served over local HTTPS
  | - reads document text/metadata
  | - stores local PowerLaw tags in document custom properties
  | - wraps generated clauses in content controls
  | - detects edits through content-control change events plus text snapshots
  v
Local PowerLaw API or HTTPS dev proxy
  |
  | /api/v1/copilot/*
  | - document identification
  | - project/contract tag confirmation
  | - generation
  | - edit + rationale capture
  v
PowerLaw event store
  |
  | append-only events + rationales
  v
Retrieval/generation memory
  |
  | prior rationales, clause edits, project facts, defined terms, conditions
  v
Future generated clauses
```

## Local API Surface

The backend exposes these routes from `routes_copilot.py`:

- `POST /api/v1/copilot/identify-document`
  - Input: filename, normalized text sample, optional document custom properties.
  - Output: candidate projects/documents with confidence and reasons.
- `POST /api/v1/copilot/confirm-document-context`
  - Input: selected `project_id`, optional `document_id`, contract type, rationale if corrected.
  - Output: canonical document context and tags to persist in Word.
- `POST /api/v1/copilot/generate`
  - Input: project/document context, selected text, requested clause/section task.
  - Output: generated text, provenance, generation event id, stable generated content id.
- `POST /api/v1/copilot/edit-observations`
  - Input: generated content id, insertion id, before text, after text, diff, required rationale.
  - Output: appended event ids and updated drafting memory status.
- `POST /api/v1/copilot/document-edit-observations`
  - Input: project/document context, before text, after text, diff, required rationale.
  - Output: appended event ids and updated drafting memory status.
- `GET /api/v1/copilot/context`
  - Input: project id, document id, optional selection text.
  - Output: defined terms, parties, relevant prior rationales, conditions, provenance snippets.

## Data Model Additions To Consider

The existing backend already has `events` and `rationales`, which should remain the spine.

Potential additions:

- `DocumentTagged`
- `DocumentContextCorrected`
- `GeneratedContentInserted`
- `GeneratedContentEdited`
- `DraftingPreferenceLearned`

Potential tables:

- `generated_contents`
  - stable id, project id, document id, segment/clause kind, prompt inputs, original text, current text
- `drafting_preferences`
  - extracted lesson from one or more rationales
  - scoped by project, document type, clause type, party/counterparty, jurisdiction, or global default

## Word Add-in Notes

For MVP, generated clauses should be inserted into Word content controls with tags like:

```text
powerlaw:generated:<generated_content_id>:<insertion_id>
```

The separate insertion id matters because the lawyer can insert the same generated
draft into multiple places. Each insertion is tracked independently.

The add-in periodically reads those content controls and compares their current
text to the last synced snapshot. It also keeps a local registry of active
insertions, so if a generated content control disappears, the rationale queue can
log it as a deletion even when Word does not fire a deletion event.

Where supported, the add-in should also register content-control `onDataChanged` and `onDeleted` handlers so the rationale queue updates quickly. Snapshot comparison should still exist as the fallback and reconciliation path.

Office add-ins should run over HTTPS even in development, so the cleanest MVP developer setup is likely:

- task pane: `https://localhost:<plugin-port>`
- backend: existing PowerLaw API on localhost
- optional proxy: task pane calls `/api/*`, dev server proxies to PowerLaw to avoid browser/CORS friction

## Run The MVP

Start the backend from the project root:

```bash
uv run uvicorn powerlaw.main:app --host 127.0.0.1 --port 8001
```

Install and start the add-in task pane from this folder:

```bash
cd plugin
npm install
npm run dev
```

Open the browser preview at:

```text
https://localhost:3101/taskpane.html
```

For Word sideloading, serve the add-in over HTTPS and copy the manifest into
Word's local sideload folder:

```bash
mkdir -p "$HOME/Library/Containers/com.microsoft.Word/Data/Documents/wef"
cp manifest.xml "$HOME/Library/Containers/com.microsoft.Word/Data/Documents/wef/powerlaw-manifest.xml"
```

The included dev server automatically serves HTTPS when these files exist:

```text
plugin/certs/localhost.pem
plugin/certs/localhost-key.pem
```

or when `POWERLAW_PLUGIN_CERT` and `POWERLAW_PLUGIN_KEY` point to certificate files.

Recommended certificate setup:

```bash
mkdir -p certs
mkcert -install
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1
```

The manifest currently points to `https://localhost:3101`. Use port `3101` for
Word, or update every `localhost:3101` URL in `manifest.xml` before sideloading.

After copying the manifest, restart Word. If the add-in is not visible on the
ribbon, use `Insert > Add-ins > My Add-ins`, select `PowerLaw Copilot`, then use
the `PowerLaw` group on the Home ribbon.

Important limitation: an Office.js task pane cannot reliably prevent every native Word save/close path. The MVP should enforce rationale before syncing edits back to PowerLaw and before using those edits as future generation memory. Later, enterprise deployment can tighten this through DMS workflow, document checkout policy, or a companion desktop integration.

Current edit-sync behavior:

- generated clauses and sections are inserted as Word content controls
- each insertion gets a unique insertion id, so the same generated text can be inserted in multiple locations
- edits inside generated content controls are detected with Office.js events plus periodic snapshot scanning
- deleted generated content controls are detected by reconciling the active insertion registry against the current Word document
- normal document body edits are detected by comparing the current body text with the last synced snapshot
- the lawyer writes rationales in the task pane and clicks `Sync all rationales`
- the task pane cannot reliably intercept Word's native Save button across desktop/web clients

## Use The Add-in

1. Open a Word document connected to a PowerLaw project, or paste text into a new document.
2. Open `PowerLaw > Open Copilot`.
3. Click `Recognize matter`.
4. Confirm the suggested project/contract tag, or choose the correct candidate.
5. Select source text in Word if the draft should respond to a specific passage.
6. Choose the content kind, write an instruction, and click `Generate`.
7. Click `Insert tracked text`.
8. Edit, delete, or move generated text in Word.
9. Add a rationale for each queued change.
10. Click `Sync rationale` or `Sync all rationales`.

## Open Product Decisions

- Should project tagging be silent when confidence is high, or always require human confirmation?
- What edits require rationale: all changes to generated text, or only substantive changes?
- Should rationale be free text only, or free text plus quick categories like `business issue`, `client preference`, `legal risk`, `negotiation position`, `factual correction`, `style`?
- Should learned preferences default to project-scoped, lawyer-scoped, or firm-wide after approval?
- Should the copilot ever rewrite directly in place, or always propose insertions for lawyer acceptance?
