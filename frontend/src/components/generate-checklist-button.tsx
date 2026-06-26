"use client";

import { useActionState } from "react";

import {
  generateChecklistAction,
  type GenerateChecklistState,
} from "@/app/actions";
import { SubmitButton } from "@/components/submit-button";

const initialState: GenerateChecklistState = {
  status: "idle",
  message: "",
  generated: 0,
};

export function GenerateChecklistButton({ projectId }: { projectId: string }) {
  const [state, formAction] = useActionState(
    generateChecklistAction.bind(null, projectId),
    initialState
  );

  return (
    <form action={formAction} className="mt-5 flex flex-col items-center gap-3">
      <SubmitButton pendingText="Generating..." icon="list-checks">
        Generate checklist
      </SubmitButton>
      {state.message ? (
        <p
          className={
            state.status === "error"
              ? "max-w-md text-sm text-destructive"
              : "max-w-md text-sm text-muted-foreground"
          }
        >
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
