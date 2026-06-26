"use client";

import { useActionState, useEffect, useRef } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { uploadDocumentsAction } from "@/app/actions";
import { SubmitButton } from "@/components/submit-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { initialUploadDocumentsState } from "@/lib/upload-state";

export function UploadDocumentsForm({ projectId }: { projectId: string }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [state, formAction] = useActionState(
    uploadDocumentsAction.bind(null, projectId),
    initialUploadDocumentsState
  );

  useEffect(() => {
    if (state.status === "success") {
      formRef.current?.reset();
    }
  }, [state.status, state.uploaded]);

  return (
    <form ref={formRef} action={formAction} className="flex flex-col gap-4">
      <div className="grid gap-2">
        <Label htmlFor="files">Documents</Label>
        <Input id="files" name="files" type="file" multiple />
      </div>

      {state.status !== "idle" ? (
        <Alert variant={state.status === "error" ? "destructive" : "default"}>
          {state.status === "error" ? (
            <AlertCircle className="size-4" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="size-4" aria-hidden="true" />
          )}
          <AlertTitle>{state.status === "error" ? "Upload failed" : "Upload complete"}</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      ) : null}

      <SubmitButton pendingText="Uploading" icon="file-up">
        Upload files
      </SubmitButton>
    </form>
  );
}
