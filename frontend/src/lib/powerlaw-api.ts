export type ProjectCounters = {
  documents_ingested: number;
  conditions_extracted: number;
  percent_satisfied: number;
  awaiting_review: number;
};

export type Project = {
  id: string;
  name: string;
  aliases: string[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type ProjectDetail = Project & {
  counters: ProjectCounters;
};

export type DocumentRecord = {
  id: string;
  project_id: string;
  type: string | null;
  title: string | null;
  filename: string;
  mime: string | null;
  execution_date: string | null;
  version: number;
  content_hash: string;
  storage_path: string | null;
  status: string | null;
  confidence: number | null;
};

export type Provenance = {
  segment_id: string;
  label: string | null;
  heading: string | null;
  document_id: string;
  document_title: string | null;
  filename: string;
  char_start: number;
  char_end: number;
  text: string;
};

export type CrossReference = {
  to_label: string;
  to_segment: string | null;
  resolved: boolean;
  source: Provenance | null;
};

export type ConditionWorkflowStatus = "open" | "ongoing" | "waived" | "verified";
export type ConditionActionStatus = "none" | "remind" | "stop" | "refresh";

export type Condition = {
  id: string;
  segment_id: string;
  project_id: string;
  beneficiary_party: string | null;
  obligor_party: string | null;
  trigger: string | null;
  requirement_text: string;
  discretionary: boolean;
  dating_rule: string | null;
  status: ConditionWorkflowStatus | string;
  waivable_by: string | null;
  confidence: number | null;
  verification_status: string;
  provenance: Provenance | null;
  source_context: Provenance | null;
  cross_refs: CrossReference[];
  dependencies: string[];
  llm_reason: string | null;
  llm_call_id: string | null;
};

export type Party = {
  id: string;
  project_id: string;
  canonical_name: string;
  entity_type: string | null;
  aliases: string[];
  roles: Array<{ document_id: string; role: string }>;
};

export type ReviewItem = {
  event_id: number;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AuditEvent = {
  id: number;
  project_id: string;
  ts: string;
  actor_id: string;
  actor_type: string;
  event_type: string;
  target_type: string | null;
  target_id: string | null;
  payload: Record<string, unknown>;
  derivation: Record<string, unknown> | null;
  rationale_id: string | null;
  rationale_text: string | null;
  rationale_author: string | null;
  caused_by: number | null;
};

export type DefinedTerm = {
  id: string;
  document_id: string | null;
  term: string;
  definition_kind: string | null;
  members: Array<{
    member_name: string;
    member_document: string | null;
    member_party: string | null;
    resolved: boolean;
  }>;
};

const API_BASE =
  process.env.POWERLAW_API_BASE_URL ??
  process.env.NEXT_PUBLIC_POWERLAW_API_BASE_URL ??
  "http://127.0.0.1:8001/api/v1";

async function requestJson<T>(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PowerLaw API ${response.status}: ${text || response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function getProjects() {
  return requestJson<ProjectDetail[]>("/projects");
}

export async function getProject(id: string) {
  return requestJson<ProjectDetail>(`/projects/${id}`);
}

export async function createProject(input: { name: string; aliases: string[] }) {
  return requestJson<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function deleteProject(projectId: string) {
  return requestJson<{ id: string; deleted: boolean }>(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function getProjectDocuments(projectId: string) {
  return requestJson<DocumentRecord[]>(`/projects/${projectId}/documents`);
}

export async function getProjectConditions(projectId: string) {
  return requestJson<Condition[]>(`/projects/${projectId}/conditions`);
}

export async function generateChecklist(projectId: string) {
  return requestJson<Condition[]>(`/projects/${projectId}/generate-checklist`, {
    method: "POST",
  });
}

export async function updateConditionStatus(input: {
  conditionId: string;
  status: ConditionWorkflowStatus;
}) {
  return requestJson<Condition>(`/conditions/${input.conditionId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      status: input.status,
      author: "dashboard",
    }),
  });
}

export async function logConditionAction(input: {
  conditionId: string;
  previousAction: ConditionActionStatus;
  action: Exclude<ConditionActionStatus, "none">;
}) {
  return requestJson<Condition>(`/conditions/${input.conditionId}/correct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      field: "action_status",
      previous_value: input.previousAction,
      new_value: input.action,
      rationale: `Frontend action changed from ${input.previousAction} to ${input.action} in the condition actions column.`,
      author: "dashboard",
    }),
  });
}

export async function getProjectParties(projectId: string) {
  return requestJson<Party[]>(`/projects/${projectId}/parties`);
}

export async function getReviewQueue(projectId: string) {
  return requestJson<ReviewItem[]>(`/projects/${projectId}/review-queue`);
}

export async function getProjectEvents(projectId: string, input?: { documentId?: string }) {
  const params = new URLSearchParams({ limit: "1000" });
  if (input?.documentId) params.set("document_id", input.documentId);
  return requestJson<AuditEvent[]>(`/projects/${projectId}/events?${params.toString()}`);
}

export async function getDefinedTerms(projectId: string) {
  return requestJson<DefinedTerm[]>(`/projects/${projectId}/defined-terms`);
}

export async function uploadProjectDocuments(projectId: string, files: File[]) {
  const body = new FormData();
  for (const file of files) {
    body.append("files", file, file.name);
  }

  const response = await fetch(`${API_BASE}/projects/${projectId}/documents`, {
    method: "POST",
    body,
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Upload failed ${response.status}: ${text || response.statusText}`);
  }

  return response.json() as Promise<
    Array<{ document_id: string; job_id: string; filename: string; status: string }>
  >;
}
