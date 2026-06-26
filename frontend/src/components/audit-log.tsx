"use client";

import { useMemo, useState } from "react";
import { FileText, History, ScrollText } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { compactId, formatDate, formatDateTime, titleize } from "@/lib/format";
import type { AuditEvent, DocumentRecord } from "@/lib/powerlaw-api";

export function AuditHistory({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No audit history"
        detail="No events have been recorded for this project yet."
      />
    );
  }

  return <AuditEventTable events={events} />;
}

export function DocumentFilesTable({
  documents,
  events,
}: {
  documents: DocumentRecord[];
  events: AuditEvent[];
}) {
  const [selectedDocument, setSelectedDocument] = useState<DocumentRecord | null>(null);
  const selectedEvents = useMemo(
    () =>
      selectedDocument
        ? events.filter((event) => eventBelongsToDocument(event, selectedDocument.id))
        : [],
    [events, selectedDocument]
  );

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No files"
        detail="Upload documents to populate this workspace."
      />
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
        <Table className="min-w-[760px]">
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Dated</TableHead>
              <TableHead>Log</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((document) => {
              const documentEvents = events.filter((event) =>
                eventBelongsToDocument(event, document.id)
              );

              return (
                <TableRow key={document.id}>
                  <TableCell className="whitespace-normal">
                    <div className="flex flex-col gap-1">
                      <span className="font-medium">{document.title ?? document.filename}</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {document.filename}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>{titleize(document.type)}</TableCell>
                  <TableCell>
                    <StatusBadge value={document.status} />
                  </TableCell>
                  <TableCell>{formatDate(document.execution_date)}</TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedDocument(document)}
                    >
                      <ScrollText className="size-3.5" aria-hidden="true" />
                      Log
                      <span className="font-mono text-xs text-muted-foreground">
                        {documentEvents.length}
                      </span>
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={Boolean(selectedDocument)}
        onOpenChange={(open) => {
          if (!open) setSelectedDocument(null);
        }}
      >
        <DialogContent className="max-h-[92vh] max-w-[calc(100%-2rem)] gap-0 overflow-hidden p-0 sm:max-w-5xl">
          {selectedDocument ? (
            <>
              <DialogHeader className="border-b p-5 pr-12">
                <DialogTitle className="text-lg">File audit log</DialogTitle>
                <DialogDescription>
                  {selectedDocument.filename} / {compactId(selectedDocument.id)}
                </DialogDescription>
              </DialogHeader>
              <ScrollArea className="max-h-[calc(92vh-100px)]">
                <div className="p-5">
                  {selectedEvents.length > 0 ? (
                    <AuditEventTable events={selectedEvents} compact />
                  ) : (
                    <EmptyState
                      icon={History}
                      title="No file events"
                      detail="No audit events are linked to this document yet."
                    />
                  )}
                </div>
              </ScrollArea>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function AuditEventTable({
  events,
  compact = false,
}: {
  events: AuditEvent[];
  compact?: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
      <Table className={compact ? "min-w-[760px]" : "min-w-[940px]"}>
        <TableHeader>
          <TableRow>
            <TableHead>Event</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Time</TableHead>
            <TableHead>Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => (
            <TableRow key={event.id}>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <span className="font-medium">{eventTypeLabel(event.event_type)}</span>
                  <span className="font-mono text-xs text-muted-foreground">#{event.id}</span>
                </div>
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <StatusBadge value={event.actor_type} />
                  <span className="font-mono text-xs text-muted-foreground">
                    {event.actor_id}
                  </span>
                </div>
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <span>{titleize(event.target_type)}</span>
                  {event.target_id ? (
                    <span className="font-mono text-xs text-muted-foreground">
                      {compactId(event.target_id)}
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="align-top whitespace-nowrap">
                {formatDateTime(event.ts)}
              </TableCell>
              <TableCell className="max-w-md whitespace-normal align-top">
                <p className="text-sm leading-6">{eventSummary(event)}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-muted-foreground">
                    Payload
                  </summary>
                  <pre className="mt-2 max-h-44 overflow-auto rounded-md bg-muted p-3 text-xs leading-5">
                    {JSON.stringify(
                      {
                        payload: event.payload,
                        derivation: event.derivation,
                        rationale: event.rationale_text,
                      },
                      null,
                      2
                    )}
                  </pre>
                </details>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function eventBelongsToDocument(event: AuditEvent, documentId: string) {
  if (event.target_type === "document" && event.target_id === documentId) return true;
  if (readString(event.payload.id) === documentId) return true;
  if (readString(event.payload.document_id) === documentId) return true;
  if (readString(event.payload.fulfilled_by_document) === documentId) return true;

  const roles = event.payload.roles;
  if (
    Array.isArray(roles) &&
    roles.some(
      (role) =>
        typeof role === "object" &&
        role !== null &&
        readString((role as Record<string, unknown>).document_id) === documentId
    )
  ) {
    return true;
  }

  const inputSpans = event.derivation?.input_spans;
  return (
    Array.isArray(inputSpans) &&
    inputSpans.some(
      (span) =>
        typeof span === "object" &&
        span !== null &&
        readString((span as Record<string, unknown>).document_id) === documentId
    )
  );
}

function eventSummary(event: AuditEvent) {
  if (event.rationale_text) return event.rationale_text;

  const reason = readString(event.payload.reason);
  if (reason) return reason;

  const error = readString(event.payload.error);
  if (error) return error;

  const field = readString(event.payload.field);
  if (field) {
    return `${titleize(field)} changed from ${displayValue(event.payload.before)} to ${displayValue(
      event.payload.after
    )}.`;
  }

  const filename = readString(event.payload.filename);
  if (filename) return `Recorded file ${filename}.`;

  const title = readString(event.payload.title);
  const type = readString(event.payload.type);
  if (title || type) return `Classified as ${titleize(type)}${title ? `: ${title}` : ""}.`;

  const status = readString(event.payload.status);
  if (status) return `Status changed to ${titleize(status)}.`;

  const term = readString(event.payload.term);
  if (term) return `Extracted defined term ${term}.`;

  const canonicalName = readString(event.payload.canonical_name);
  if (canonicalName) return `Identified party ${canonicalName}.`;

  const derivationReason = readString(event.derivation?.reason);
  if (derivationReason) return derivationReason;

  return "Recorded audit event.";
}

function eventTypeLabel(value: string) {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function readString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function displayValue(value: unknown) {
  if (value === null || value === undefined) return "empty";
  if (typeof value === "string") return titleize(value);
  return JSON.stringify(value);
}
