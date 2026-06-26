"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { updateConditionStatusAction } from "@/app/actions";
import type { ConditionWorkflowStatus } from "@/lib/powerlaw-api";

const statusOptions = [
  { value: "open", label: "Open" },
  { value: "ongoing", label: "Ongoing" },
  { value: "waived", label: "Waived" },
  { value: "verified", label: "Verified" },
] satisfies Array<{ value: ConditionWorkflowStatus; label: string }>;

const statusValues = new Set(statusOptions.map((option) => option.value));

export function ConditionStatusControl({
  conditionId,
  projectId,
  status,
}: {
  conditionId: string;
  projectId: string;
  status: string;
}) {
  const router = useRouter();
  const normalizedStatus = statusValues.has(status as ConditionWorkflowStatus)
    ? (status as ConditionWorkflowStatus)
    : "open";
  const [selected, setSelected] = useState<ConditionWorkflowStatus>(normalizedStatus);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  return (
    <div className="grid gap-1">
      <label className="sr-only" htmlFor={`condition-status-${conditionId}`}>
        Condition status
      </label>
      <select
        id={`condition-status-${conditionId}`}
        value={selected}
        disabled={isPending}
        onChange={(event) => {
          const nextStatus = event.target.value as ConditionWorkflowStatus;
          const previous = selected;
          setSelected(nextStatus);
          setError(null);
          startTransition(async () => {
            try {
              await updateConditionStatusAction(conditionId, projectId, nextStatus);
              router.refresh();
            } catch (caught) {
              setSelected(previous);
              setError(caught instanceof Error ? caught.message : "Status update failed.");
            }
          });
        }}
        className="h-8 min-w-28 rounded-md border border-input bg-background px-2 text-sm outline-none transition-colors focus:border-ring focus:ring-3 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {statusOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? <p className="max-w-32 text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
