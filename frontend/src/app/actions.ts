"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  createProject,
  deleteProject,
  generateChecklist,
  logConditionAction,
  updateConditionStatus,
  uploadProjectDocuments,
} from "@/lib/powerlaw-api";
import type { ConditionActionStatus, ConditionWorkflowStatus } from "@/lib/powerlaw-api";
import type { UploadDocumentsState } from "@/lib/upload-state";

export type GenerateChecklistState = {
  status: "idle" | "success" | "error";
  message: string;
  generated: number;
};

export async function createProjectAction(formData: FormData) {
  const name = String(formData.get("name") ?? "").trim();
  const aliases = String(formData.get("aliases") ?? "")
    .split(",")
    .map((alias) => alias.trim())
    .filter(Boolean);

  if (!name) {
    throw new Error("Project name is required.");
  }

  const project = await createProject({ name, aliases });
  revalidatePath("/");
  redirect(`/projects/${project.id}`);
}

export async function deleteProjectAction(projectId: string) {
  await deleteProject(projectId);
  revalidatePath("/");
}

export async function generateChecklistAction(
  projectId: string,
  _state: GenerateChecklistState
): Promise<GenerateChecklistState> {
  void _state;

  try {
    const conditions = await generateChecklist(projectId);
    revalidatePath("/");
    revalidatePath(`/projects/${projectId}`);
    const noun = conditions.length === 1 ? "condition" : "conditions";

    return {
      status: "success",
      message: `Generated ${conditions.length} checklist ${noun}.`,
      generated: conditions.length,
    };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Checklist generation failed.",
      generated: 0,
    };
  }
}

export async function updateConditionStatusAction(
  conditionId: string,
  projectId: string,
  status: ConditionWorkflowStatus
) {
  await updateConditionStatus({ conditionId, status });
  revalidatePath("/");
  revalidatePath(`/projects/${projectId}`);
}

export async function logConditionActionSelectionAction(
  conditionId: string,
  previousAction: ConditionActionStatus,
  action: Exclude<ConditionActionStatus, "none">
) {
  await logConditionAction({ conditionId, previousAction, action });
}

export async function uploadDocumentsAction(
  projectId: string,
  _state: UploadDocumentsState,
  formData: FormData
): Promise<UploadDocumentsState> {
  const files = formData
    .getAll("files")
    .filter((file): file is File => file instanceof File && file.size > 0);

  if (files.length === 0) {
    return {
      status: "error",
      message: "Choose at least one document.",
      uploaded: 0,
    };
  }

  try {
    const uploaded = await uploadProjectDocuments(projectId, files);
    revalidatePath("/");
    revalidatePath(`/projects/${projectId}`);
    const noun = uploaded.length === 1 ? "file" : "files";

    return {
      status: "success",
      message: `Uploaded ${uploaded.length} ${noun}.`,
      uploaded: uploaded.length,
    };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Upload failed.",
      uploaded: 0,
    };
  }
}
