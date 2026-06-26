const API_BASE = localStorage.getItem("powerlaw_api_base") || "/api/v1";
const GENERATED_TAG_PREFIX = "powerlaw:generated:";
const SNAPSHOT_KEY = "powerlaw_generated_snapshots";
const ACTIVE_INSERTIONS_KEY = "powerlaw_active_insertions";
const DOCUMENT_SNAPSHOT_KEY = "powerlaw_document_snapshot";
const PENDING_KEY = "powerlaw_pending_edits";
const LOCAL_TAGS_KEY = "powerlaw_document_tags";
const TRACK_SCAN_INTERVAL_MS = 4000;

const elements = {
  runtimeStatus: document.querySelector("#runtimeStatus"),
  contextTitle: document.querySelector("#contextTitle"),
  matterName: document.querySelector("#matterName"),
  matterMeta: document.querySelector("#matterMeta"),
  previewText: document.querySelector("#previewText"),
  identifyButton: document.querySelector("#identifyButton"),
  refreshContextButton: document.querySelector("#refreshContextButton"),
  scanButton: document.querySelector("#scanButton"),
  candidateList: document.querySelector("#candidateList"),
  contentKind: document.querySelector("#contentKind"),
  draftInstruction: document.querySelector("#draftInstruction"),
  generateButton: document.querySelector("#generateButton"),
  insertButton: document.querySelector("#insertButton"),
  draftOutput: document.querySelector("#draftOutput"),
  queueCount: document.querySelector("#queueCount"),
  rationaleQueue: document.querySelector("#rationaleQueue"),
  syncAllButton: document.querySelector("#syncAllButton"),
  messageLog: document.querySelector("#messageLog"),
};

const state = {
  officeReady: false,
  context: null,
  candidates: [],
  generated: null,
  snapshots: readJson(SNAPSHOT_KEY, {}),
  activeInsertions: readJson(ACTIVE_INSERTIONS_KEY, {}),
  documentSnapshot: localStorage.getItem(DOCUMENT_SNAPSHOT_KEY) || "",
  pendingEdits: readJson(PENDING_KEY, []),
  registeredControls: new Set(),
  hasAutoRecognized: false,
  scanTimer: null,
  scanInFlight: false,
};

elements.identifyButton.addEventListener("click", () => identifyDocument());
elements.refreshContextButton.addEventListener("click", () => refreshContext());
elements.scanButton.addEventListener("click", () => scanTrackedClauses());
elements.generateButton.addEventListener("click", generateDraft);
elements.insertButton.addEventListener("click", insertGeneratedText);
elements.syncAllButton.addEventListener("click", syncAllRationales);

renderQueue();
bootstrapOffice();

function bootstrapOffice() {
  if (!globalThis.Office) {
    elements.runtimeStatus.textContent = "Browser preview";
    void initializePane();
    return;
  }

  Office.onReady((info) => {
    state.officeReady = info.host === Office.HostType.Word;
    elements.runtimeStatus.textContent = state.officeReady ? "Word connected" : "Office loaded";
    void initializePane();
  });
}

async function initializePane() {
  await refreshContext({ silent: true });
  if (!state.context) {
    await autoRecognizeMatter();
  }
  if (state.officeReady) {
    await initializeDocumentSnapshot();
    await scanTrackedClauses({ silent: true });
    await scanDocumentChanges({ silent: true });
    startEditTracking();
  }
}

async function refreshContext(options = {}) {
  try {
    const tags = await readDocumentTags();
    if (tags.powerlaw_project_id) {
      state.context = {
        project_id: tags.powerlaw_project_id,
        document_id: tags.powerlaw_document_id || null,
        project_name: tags.powerlaw_project_name || "Tagged PowerLaw project",
        contract_type: tags.powerlaw_contract_type || null,
      };
    } else {
      state.context = null;
    }
    renderContext();
    if (!options.silent) {
      logMessage("Context refreshed.");
    }
  } catch (error) {
    logError(error);
  }
}

async function autoRecognizeMatter() {
  if (state.hasAutoRecognized) {
    return;
  }
  state.hasAutoRecognized = true;
  logMessage("Scanning current document for a PowerLaw matter.");
  await identifyDocument({ automatic: true });
}

async function identifyDocument(options = {}) {
  const automatic = options.automatic === true;
  setBusy(elements.identifyButton, true, automatic ? "Scanning" : "Recognizing");
  try {
    const probe = await readDocumentProbe();
    const response = await api("/copilot/identify-document", {
      method: "POST",
      body: JSON.stringify(probe),
    });
    state.candidates = response.candidates || [];
    renderCandidates();
    if (state.candidates.length === 0) {
      logMessage("No project match found. Create or ingest the project in PowerLaw first.");
    } else if (response.needs_confirmation) {
      logMessage("PowerLaw found a likely match. Confirm or choose the right matter.");
    } else {
      logMessage("PowerLaw recognized this matter with high confidence. Confirm to save the tag.");
    }
  } catch (error) {
    logError(error);
  } finally {
    setBusy(elements.identifyButton, false, "Recognize matter");
  }
}

async function confirmCandidate(candidate, corrected) {
  try {
    const response = await api("/copilot/confirm-document-context", {
      method: "POST",
      body: JSON.stringify({
        project_id: candidate.project_id,
        document_id: candidate.document_id,
        contract_type: inferContractType(candidate),
        corrected,
        rationale: corrected ? "Selected the correct matter from Word add-in suggestions." : null,
        author: "word-addin",
      }),
    });
    await writeDocumentTags(response.tags);
    state.context = {
      project_id: response.project_id,
      document_id: response.document_id,
      project_name: response.tags.powerlaw_project_name,
      contract_type: response.contract_type,
    };
    elements.candidateList.innerHTML = "";
    renderContext();
    logMessage("Matter tag saved to the Word document.");
  } catch (error) {
    logError(error);
  }
}

async function generateDraft() {
  if (!state.context?.project_id) {
    logMessage("Tag the matter before generating language.");
    return;
  }
  setBusy(elements.generateButton, true, "Generating");
  try {
    const selectedText = await readSelectionText();
    const contentKind = elements.contentKind.value || "clause";
    const response = await api("/copilot/generate", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.context.project_id,
        document_id: state.context.document_id,
        instruction: elements.draftInstruction.value.trim(),
        selected_text: selectedText,
        content_kind: contentKind,
        author: "word-addin",
      }),
    });
    state.generated = { ...response, content_kind: contentKind };
    elements.draftOutput.textContent = response.text;
    elements.insertButton.disabled = false;
    logMessage("Draft ready. Insert it to track future edits.");
  } catch (error) {
    logError(error);
  } finally {
    setBusy(elements.generateButton, false, "Generate");
  }
}

async function insertGeneratedText() {
  if (!state.generated) {
    return;
  }

  if (!state.officeReady || !globalThis.Word) {
    elements.previewText.value = `${elements.previewText.value}\n\n${state.generated.text}`.trim();
    const insertionId = crypto.randomUUID();
    rememberSnapshot(insertionId, state.generated.text);
    logMessage("Inserted into preview text. Word insertion runs inside the add-in.");
    return;
  }

  try {
    await Word.run(async (context) => {
      const selection = context.document.getSelection();
      const inserted = selection.insertText(state.generated.text, Word.InsertLocation.replace);
      const control = inserted.insertContentControl();
      const insertionId = crypto.randomUUID();
      const contentKind = state.generated.content_kind || "text";
      control.tag = `${GENERATED_TAG_PREFIX}${state.generated.generated_content_id}:${insertionId}`;
      control.title = `PowerLaw generated ${contentKind}`;
      control.appearance = "BoundingBox";
      control.color = "#2f7a73";
      await context.sync();
      rememberSnapshot(insertionId, state.generated.text);
      rememberActiveInsertion({
        generated_content_id: state.generated.generated_content_id,
        insertion_id: insertionId,
        content_kind: contentKind,
      });
    });
    await initializeDocumentSnapshot({ force: true });
    elements.insertButton.disabled = false;
    logMessage("Inserted tracked text. You can insert the same draft again elsewhere.");
    await scanTrackedClauses();
  } catch (error) {
    logError(error);
  }
}

async function scanTrackedClauses(options = {}) {
  const silent = options.silent === true;
  if (!state.officeReady || !globalThis.Word) {
    renderQueue();
    if (!silent) {
      logMessage("Browser preview has no Word content controls to scan.");
    }
    return;
  }
  if (state.scanInFlight) {
    return;
  }
  state.scanInFlight = true;

  try {
    const seenInsertions = new Set();
    let deletedGeneratedContent = false;
    await Word.run(async (context) => {
      const controls = context.document.contentControls;
      controls.load("items/id,tag,text,title");
      await context.sync();

      for (const control of controls.items) {
        if (!control.tag || !control.tag.startsWith(GENERATED_TAG_PREFIX)) {
          continue;
        }
        const tag = parseGeneratedTag(control.tag);
        if (!tag) {
          continue;
        }
        const contentKind = contentKindFromTitle(control.title);
        seenInsertions.add(tag.insertion_id);
        rememberActiveInsertion({
          generated_content_id: tag.generated_content_id,
          insertion_id: tag.insertion_id,
          content_kind: contentKind,
        });
        registerControlEvents(control, tag);
        const before = state.snapshots[tag.insertion_id];
        if (before === undefined) {
          rememberSnapshot(tag.insertion_id, control.text);
          continue;
        }
        if (before !== control.text) {
          queueEdit({
            scope: "generated",
            generated_content_id: tag.generated_content_id,
            insertion_id: tag.insertion_id,
            content_kind: contentKind,
            before_text: before,
            after_text: control.text,
            diff: diffSummary(before, control.text),
          });
        }
      }
    });
    deletedGeneratedContent = queueDeletedGeneratedContent(seenInsertions);
    renderQueue();
    if (!silent) {
      logMessage(
        deletedGeneratedContent
          ? "Tracked generated text deletion found. Add a rationale to sync it."
          : "Tracked generated text scanned.",
      );
    }
  } catch (error) {
    if (!silent) {
      logError(error);
    }
  } finally {
    state.scanInFlight = false;
  }
}

function registerControlEvents(control, tag) {
  if (state.registeredControls.has(tag.insertion_id)) {
    return;
  }
  try {
    if (control.onDataChanged) {
      control.onDataChanged.add(() => scanTrackedClauses({ silent: true }));
    }
    if (control.onDeleted) {
      control.onDeleted.add(() => {
        const before = state.snapshots[tag.insertion_id] || "";
        if (before) {
          queueEdit({
            scope: "generated",
            generated_content_id: tag.generated_content_id,
            insertion_id: tag.insertion_id,
            content_kind: contentKindFromTitle(control.title),
            before_text: before,
            after_text: "",
            diff: diffSummary(before, ""),
          });
          renderQueue();
          logMessage("Tracked generated text was deleted. Add a rationale to sync it.");
        }
      });
    }
    state.registeredControls.add(tag.insertion_id);
  } catch {
    // Snapshot scanning remains the reconciliation path when events are unavailable.
  }
}

function startEditTracking() {
  if (!state.officeReady || state.scanTimer) {
    return;
  }
  state.scanTimer = globalThis.setInterval(() => {
    scanTrackedClauses({ silent: true });
    scanDocumentChanges({ silent: true });
  }, TRACK_SCAN_INTERVAL_MS);
}

async function submitRationale(editId) {
  const edit = state.pendingEdits.find((item) => item.local_id === editId);
  if (!edit || !state.context?.project_id) {
    return;
  }
  const textArea = document.querySelector(`[data-rationale="${editId}"]`);
  const rationale = textArea?.value.trim() || "";
  if (!rationale) {
    logMessage("Add a rationale before syncing this edit.");
    textArea?.focus();
    return;
  }
  const categories = Array.from(
    document.querySelectorAll(`[data-category-for="${editId}"]:checked`),
  ).map((input) => input.value);

  try {
    await submitEdit(edit, rationale, categories);
    removePendingEdit(edit.local_id);
    logMessage("Rationale synced to PowerLaw.");
  } catch (error) {
    logError(error);
  }
}

async function syncAllRationales() {
  if (!state.context?.project_id || state.pendingEdits.length === 0) {
    return;
  }

  const drafts = collectRationaleDrafts();
  const missing = state.pendingEdits.find((edit) => !drafts[edit.local_id]?.rationale);
  if (missing) {
    logMessage("Every queued edit needs a rationale before syncing all.");
    document.querySelector(`[data-rationale="${missing.local_id}"]`)?.focus();
    return;
  }

  setBusy(elements.syncAllButton, true, "Syncing");
  try {
    for (const edit of [...state.pendingEdits]) {
      if (!state.pendingEdits.some((item) => item.local_id === edit.local_id)) {
        continue;
      }
      const draft = drafts[edit.local_id];
      await submitEdit(edit, draft.rationale, draft.categories);
      removePendingEdit(edit.local_id, { render: false });
    }
    renderQueue();
    logMessage("All rationales synced to PowerLaw.");
  } catch (error) {
    logError(error);
  } finally {
    setBusy(elements.syncAllButton, false, "Sync all rationales");
  }
}

async function submitEdit(edit, rationale, categories) {
  if (edit.scope === "document") {
    await api("/copilot/document-edit-observations", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.context.project_id,
        document_id: state.context.document_id,
        before_text: edit.before_text,
        after_text: edit.after_text,
        rationale,
        categories,
        author: "word-addin",
      }),
    });
    state.documentSnapshot = edit.after_text;
    localStorage.setItem(DOCUMENT_SNAPSHOT_KEY, edit.after_text);
    return;
  }

  await api("/copilot/edit-observations", {
    method: "POST",
    body: JSON.stringify({
      project_id: state.context.project_id,
      document_id: state.context.document_id,
      generated_content_id: edit.generated_content_id,
      insertion_id: edit.insertion_id,
      before_text: edit.before_text,
      after_text: edit.after_text,
      rationale,
      categories,
      author: "word-addin",
    }),
  });
  if (edit.after_text) {
    rememberSnapshot(edit.insertion_id, edit.after_text);
    rememberActiveInsertion({
      generated_content_id: edit.generated_content_id,
      insertion_id: edit.insertion_id,
      content_kind: edit.content_kind || "text",
    });
  } else {
    forgetActiveInsertion(edit.insertion_id);
  }
  dropGeneratedOnlyDocumentQueues(edit);
  await initializeDocumentSnapshot({ force: true });
}

function removePendingEdit(editId, options = {}) {
  const render = options.render !== false;
  state.pendingEdits = state.pendingEdits.filter((item) => item.local_id !== editId);
  writeJson(PENDING_KEY, state.pendingEdits);
  if (render) {
    renderQueue();
  }
}

async function readDocumentProbe() {
  const customProperties = await readDocumentTags();
  const text = state.officeReady ? await readBodyText() : elements.previewText.value;
  return {
    filename: customProperties.powerlaw_filename || "Word document",
    text: text.slice(0, 20000),
    custom_properties: customProperties,
    max_candidates: 5,
  };
}

async function readBodyText() {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load("text");
    await context.sync();
    return body.text || "";
  });
}

async function readSelectionText() {
  if (!state.officeReady || !globalThis.Word) {
    return elements.previewText.value;
  }
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load("text");
    await context.sync();
    return selection.text || "";
  });
}

async function initializeDocumentSnapshot(options = {}) {
  if (!state.officeReady || !globalThis.Word) {
    return;
  }
  const currentText = await readBodyText();
  if (options.force || !state.documentSnapshot) {
    state.documentSnapshot = currentText;
    localStorage.setItem(DOCUMENT_SNAPSHOT_KEY, currentText);
  }
}

async function scanDocumentChanges(options = {}) {
  const silent = options.silent === true;
  if (!state.officeReady || !globalThis.Word || !state.context?.project_id) {
    return;
  }
  try {
    const currentText = await readBodyText();
    if (!state.documentSnapshot) {
      state.documentSnapshot = currentText;
      localStorage.setItem(DOCUMENT_SNAPSHOT_KEY, currentText);
      return;
    }
    const expectedText = documentSnapshotAdjustedForGeneratedEdits();
    if (expectedText === currentText) {
      state.documentSnapshot = currentText;
      localStorage.setItem(DOCUMENT_SNAPSHOT_KEY, currentText);
      return;
    }
    if (state.documentSnapshot !== currentText) {
      queueDocumentEdit(expectedText, currentText);
      renderQueue();
      if (!silent) {
        logMessage("Document edit detected. Add a rationale before syncing.");
      }
    }
  } catch (error) {
    if (!silent) {
      logError(error);
    }
  }
}

async function readDocumentTags() {
  if (!state.officeReady || !globalThis.Word) {
    return readJson(LOCAL_TAGS_KEY, {});
  }

  return Word.run(async (context) => {
    const properties = context.document.properties;
    properties.load("title");
    const customProperties = properties.customProperties;
    customProperties.load("key,value");
    await context.sync();
    const tags = {};
    for (const property of customProperties.items) {
      if (property.key.startsWith("powerlaw_")) {
        tags[property.key] = String(property.value);
      }
    }
    if (properties.title) {
      tags.powerlaw_filename = properties.title;
    }
    return tags;
  });
}

async function writeDocumentTags(tags) {
  writeJson(LOCAL_TAGS_KEY, { ...readJson(LOCAL_TAGS_KEY, {}), ...tags });
  if (!state.officeReady || !globalThis.Word) {
    return;
  }

  await Word.run(async (context) => {
    const customProperties = context.document.properties.customProperties;
    for (const [key, value] of Object.entries(tags)) {
      customProperties.add(key, value);
    }
    await context.sync();
  });
}

function renderContext() {
  if (!state.context) {
    elements.contextTitle.textContent = "No matter tagged";
    elements.matterName.textContent = "Open a Word document or use preview text.";
    elements.matterMeta.textContent = "PowerLaw will suggest the project and contract tag.";
    return;
  }
  elements.contextTitle.textContent = "Matter tagged";
  elements.matterName.textContent = state.context.project_name || state.context.project_id;
  const detail = [state.context.contract_type, state.context.document_id]
    .filter(Boolean)
    .join(" | ");
  elements.matterMeta.textContent = detail || "Project context saved in the document.";
}

function renderCandidates() {
  if (state.candidates.length === 0) {
    elements.candidateList.innerHTML = '<p class="empty-note">No candidates yet.</p>';
    return;
  }
  elements.candidateList.innerHTML = "";
  state.candidates.forEach((candidate, index) => {
    const card = document.createElement("article");
    card.className = "candidate-card";
    const reasons = candidate.reasons?.join("; ") || "Matched by document signals.";
    const actionLabel = index === 0 ? "Confirm tag" : "Use this tag";
    card.innerHTML = `
      <strong>${escapeHtml(candidate.project_name)}</strong>
      <p class="candidate-reasons">${escapeHtml(reasons)}</p>
      <div class="candidate-actions">
        <span class="confidence">${Math.round(candidate.confidence * 100)}%</span>
        <button class="primary-button" type="button">${actionLabel}</button>
      </div>
    `;
    card.querySelector("button").addEventListener("click", () => {
      confirmCandidate(candidate, index !== 0 || candidate.requires_confirmation);
    });
    elements.candidateList.appendChild(card);
  });
}

function renderQueue() {
  elements.queueCount.textContent = String(state.pendingEdits.length);
  if (state.pendingEdits.length === 0) {
    elements.rationaleQueue.innerHTML =
      '<p class="empty-note">Generated text edits and normal document edits will appear here.</p>';
    elements.syncAllButton.disabled = true;
    return;
  }

  elements.rationaleQueue.innerHTML = "";
  elements.syncAllButton.disabled = false;
  state.pendingEdits.forEach((edit) => {
    const kind = edit.scope === "document" ? "document" : edit.content_kind || "text";
    const card = document.createElement("article");
    card.className = "queue-card";
    card.innerHTML = `
      <strong>${escapeHtml(queueTitle(edit, kind))}</strong>
      <pre class="queue-diff">${escapeHtml(edit.diff)}</pre>
      <div class="category-row">
        ${categoryCheckbox(edit.local_id, "business issue")}
        ${categoryCheckbox(edit.local_id, "legal risk")}
        ${categoryCheckbox(edit.local_id, "client preference")}
        ${categoryCheckbox(edit.local_id, "style")}
      </div>
      <textarea class="rationale-input" rows="3" data-rationale="${edit.local_id}" placeholder="Why did you make this edit?">${escapeHtml(edit.rationale || "")}</textarea>
      <div class="queue-actions">
        <button class="primary-button" type="button">Sync rationale</button>
      </div>
    `;
    card.querySelector("textarea").addEventListener("input", (event) => {
      edit.rationale = event.target.value;
      writeJson(PENDING_KEY, state.pendingEdits);
    });
    card.querySelectorAll("input[type='checkbox']").forEach((input) => {
      input.checked = (edit.categories || []).includes(input.value);
      input.addEventListener("change", () => {
        edit.categories = Array.from(
          card.querySelectorAll("input[type='checkbox']:checked"),
        ).map((item) => item.value);
        writeJson(PENDING_KEY, state.pendingEdits);
      });
    });
    card.querySelector("button").addEventListener("click", () => submitRationale(edit.local_id));
    elements.rationaleQueue.appendChild(card);
  });
}

function queueEdit(edit) {
  const existing = state.pendingEdits.find(
    (item) =>
      item.scope === "generated" &&
      item.generated_content_id === edit.generated_content_id &&
      item.insertion_id === edit.insertion_id,
  );
  if (existing) {
    existing.before_text = edit.before_text;
    existing.after_text = edit.after_text;
    existing.diff = edit.diff;
  } else {
    state.pendingEdits.push({
      local_id: crypto.randomUUID(),
      ...edit,
    });
  }
  writeJson(PENDING_KEY, state.pendingEdits);
}

function queueDocumentEdit(beforeText, afterText) {
  const existing = state.pendingEdits.find((item) => item.scope === "document");
  if (existing) {
    existing.before_text = beforeText;
    existing.after_text = afterText;
    existing.diff = diffSummary(beforeText, afterText);
  } else {
    state.pendingEdits.push({
      local_id: crypto.randomUUID(),
      scope: "document",
      before_text: beforeText,
      after_text: afterText,
      diff: diffSummary(beforeText, afterText),
      categories: [],
      rationale: "",
    });
  }
  writeJson(PENDING_KEY, state.pendingEdits);
}

function rememberSnapshot(generatedId, text) {
  state.snapshots[generatedId] = text;
  writeJson(SNAPSHOT_KEY, state.snapshots);
}

function rememberActiveInsertion(insertion) {
  const documentKey = activeDocumentKey();
  if (!documentKey || !insertion.insertion_id) {
    return;
  }
  state.activeInsertions[insertion.insertion_id] = {
    ...insertion,
    document_key: documentKey,
  };
  writeJson(ACTIVE_INSERTIONS_KEY, state.activeInsertions);
}

function forgetActiveInsertion(insertionId) {
  delete state.activeInsertions[insertionId];
  delete state.snapshots[insertionId];
  writeJson(ACTIVE_INSERTIONS_KEY, state.activeInsertions);
  writeJson(SNAPSHOT_KEY, state.snapshots);
}

function queueDeletedGeneratedContent(seenInsertions) {
  const documentKey = activeDocumentKey();
  if (!documentKey) {
    return false;
  }

  let queued = false;
  for (const [insertionId, insertion] of Object.entries(state.activeInsertions)) {
    if (insertion.document_key !== documentKey || seenInsertions.has(insertionId)) {
      continue;
    }
    if (hasPendingGeneratedEdit(insertionId)) {
      continue;
    }
    const before = state.snapshots[insertionId] || "";
    if (!before) {
      continue;
    }
    queueEdit({
      scope: "generated",
      generated_content_id: insertion.generated_content_id,
      insertion_id: insertionId,
      content_kind: insertion.content_kind || "text",
      before_text: before,
      after_text: "",
      diff: diffSummary(before, ""),
    });
    queued = true;
  }
  return queued;
}

function hasPendingGeneratedEdit(insertionId) {
  return state.pendingEdits.some(
    (item) => item.scope === "generated" && item.insertion_id === insertionId,
  );
}

function dropGeneratedOnlyDocumentQueues(submittedEdit) {
  const beforeCount = state.pendingEdits.length;
  state.pendingEdits = state.pendingEdits.filter((item) => {
    if (item.scope !== "document") {
      return true;
    }
    const afterGeneratedEdit = replaceFirst(
      item.before_text,
      submittedEdit.before_text,
      submittedEdit.after_text,
    );
    return afterGeneratedEdit !== item.after_text;
  });
  if (state.pendingEdits.length !== beforeCount) {
    writeJson(PENDING_KEY, state.pendingEdits);
  }
}

function documentSnapshotAdjustedForGeneratedEdits() {
  return state.pendingEdits
    .filter((edit) => edit.scope === "generated")
    .reduce(
      (text, edit) => replaceFirst(text, edit.before_text, edit.after_text),
      state.documentSnapshot,
    );
}

function replaceFirst(text, search, replacement) {
  if (!search) {
    return text;
  }
  const index = text.indexOf(search);
  if (index === -1) {
    return text;
  }
  return `${text.slice(0, index)}${replacement}${text.slice(index + search.length)}`;
}

function activeDocumentKey() {
  if (!state.context?.project_id) {
    return "";
  }
  return [state.context.project_id, state.context.document_id || "untitled"].join(":");
}

function parseGeneratedTag(tag) {
  if (!tag || !tag.startsWith(GENERATED_TAG_PREFIX)) {
    return null;
  }
  const raw = tag.slice(GENERATED_TAG_PREFIX.length);
  const [generatedId, insertionId] = raw.split(":");
  return {
    generated_content_id: generatedId,
    insertion_id: insertionId || generatedId,
  };
}

function collectRationaleDrafts() {
  const drafts = {};
  for (const edit of state.pendingEdits) {
    const textArea = document.querySelector(`[data-rationale="${edit.local_id}"]`);
    drafts[edit.local_id] = {
      rationale: textArea?.value.trim() || edit.rationale || "",
      categories: Array.from(
        document.querySelectorAll(`[data-category-for="${edit.local_id}"]:checked`),
      ).map((input) => input.value),
    };
  }
  return drafts;
}

function queueTitle(edit, kind) {
  if (edit.scope === "document") {
    return "Document changed";
  }
  if (!edit.after_text) {
    return `Generated ${kind} deleted`;
  }
  return `Generated ${kind} changed`;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`PowerLaw API ${response.status}: ${detail || response.statusText}`);
  }
  return response.json();
}

function inferContractType(candidate) {
  const label = `${candidate.document_title || ""} ${candidate.filename || ""}`.toLowerCase();
  if (label.includes("financing")) {
    return "financing_agreement";
  }
  if (label.includes("credit")) {
    return "credit_agreement";
  }
  if (label.includes("lease")) {
    return "lease";
  }
  return null;
}

function diffSummary(before, after) {
  const beforeText = compact(before);
  const afterText = compact(after);
  return `Before:\n${beforeText.slice(0, 700)}\n\nAfter:\n${afterText.slice(0, 700)}`;
}

function contentKindFromTitle(title) {
  const normalized = String(title || "").toLowerCase();
  if (normalized.includes("section")) {
    return "section";
  }
  if (normalized.includes("clause")) {
    return "clause";
  }
  return "text";
}

function compact(value) {
  return value.replace(/\s+/g, " ").trim();
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.textContent = label;
}

function logMessage(message) {
  elements.messageLog.textContent = message;
  elements.messageLog.classList.remove("error-text");
}

function logError(error) {
  elements.messageLog.textContent = error instanceof Error ? error.message : String(error);
  elements.messageLog.classList.add("error-text");
}

function readJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || "") || fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function categoryCheckbox(editId, value) {
  const escaped = escapeHtml(value);
  return `
    <label>
      <input type="checkbox" value="${escaped}" data-category-for="${editId}">
      ${escaped}
    </label>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
