"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { BookOpenText, GitBranch, ListChecks, Sparkles } from "lucide-react";

import { ConditionActionControl } from "@/components/condition-action-control";
import { ConditionStatusControl } from "@/components/condition-status-control";
import { EmptyState } from "@/components/empty-state";
import { GenerateChecklistButton } from "@/components/generate-checklist-button";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { compactId, titleize } from "@/lib/format";
import type { Condition, Provenance } from "@/lib/powerlaw-api";

export function ConditionsWorkspace({
  conditions,
  projectId,
  hasDocuments,
}: {
  conditions: Condition[];
  projectId: string;
  hasDocuments: boolean;
}) {
  const [selected, setSelected] = useState<Condition | null>(null);

  if (conditions.length === 0) {
    return (
      <div>
        <EmptyState
          icon={ListChecks}
          title="No conditions"
          detail={
            hasDocuments
              ? "No checklist conditions have been generated for this project."
              : "Upload documents before generating a checklist."
          }
        />
        {hasDocuments ? <GenerateChecklistButton projectId={projectId} /> : null}
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
        <Table className="min-w-[1020px]">
          <TableHeader>
            <TableRow>
              <TableHead>Source</TableHead>
              <TableHead>Requirement</TableHead>
              <TableHead>Trigger</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {conditions.map((condition) => (
              <TableRow key={condition.id}>
                <TableCell className="align-top">
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-auto max-w-44 justify-start px-0 py-0 text-left"
                    onClick={() => setSelected(condition)}
                  >
                    <span className="border-l-2 border-provenance pl-3">
                      <span className="block font-mono text-sm">
                        {condition.provenance?.label ?? "n/a"}
                      </span>
                      <span className="mt-1 block whitespace-normal text-xs text-muted-foreground">
                        {condition.provenance?.filename ?? "No source"}
                      </span>
                    </span>
                  </Button>
                </TableCell>
                <TableCell className="max-w-xl whitespace-normal align-top">
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-auto w-full justify-start whitespace-normal px-0 py-0 text-left text-sm font-normal leading-6"
                    onClick={() => setSelected(condition)}
                  >
                    <span className="line-clamp-3">{condition.requirement_text}</span>
                  </Button>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {condition.discretionary ? (
                      <Badge variant="secondary">Discretionary</Badge>
                    ) : null}
                    {condition.cross_refs.length > 0 ? (
                      <Badge variant="outline">
                        {condition.cross_refs.length} cross refs
                      </Badge>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-top">{titleize(condition.trigger)}</TableCell>
                <TableCell className="align-top">
                  <ConditionStatusControl
                    conditionId={condition.id}
                    projectId={projectId}
                    status={condition.status}
                  />
                </TableCell>
                <TableCell className="align-top">
                  <ConditionActionControl conditionId={condition.id} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ConditionDetailDialog
        condition={selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      />
    </>
  );
}

function ConditionDetailDialog({
  condition,
  onOpenChange,
}: {
  condition: Condition | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={Boolean(condition)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-[calc(100%-2rem)] gap-0 overflow-hidden p-0 sm:max-w-4xl">
        {condition ? (
          <>
            <DialogHeader className="border-b p-5 pr-12">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{condition.provenance?.label ?? "Condition"}</Badge>
                <StatusBadge value={condition.status} />
              </div>
              <DialogTitle className="mt-3 text-lg">Condition context</DialogTitle>
              <DialogDescription>
                {condition.provenance?.filename ?? "Unknown source"} /{" "}
                {compactId(condition.id)}
              </DialogDescription>
            </DialogHeader>

            <ScrollArea className="max-h-[calc(92vh-132px)]">
              <div className="grid gap-6 p-5">
                <section className="grid gap-3">
                  <SectionHeading icon={ListChecks} label="Requirement" />
                  <p className="text-sm leading-6">{condition.requirement_text}</p>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{titleize(condition.trigger)}</Badge>
                    {condition.dating_rule ? (
                      <Badge variant="outline">{titleize(condition.dating_rule)}</Badge>
                    ) : null}
                    {condition.discretionary ? (
                      <Badge variant="secondary">Discretionary</Badge>
                    ) : null}
                  </div>
                  {condition.waivable_by ? (
                    <p className="text-sm text-muted-foreground">
                      Waivable by {condition.waivable_by}
                    </p>
                  ) : null}
                </section>

                <Separator />

                <section className="grid gap-3">
                  <SectionHeading icon={Sparkles} label="LLM reason" />
                  <p className="text-sm leading-6 text-muted-foreground">
                    {condition.llm_reason ??
                      "No LLM reason is stored for this condition. It may have been generated by the deterministic extractor or created before LLM logging was added."}
                  </p>
                  {condition.llm_call_id ? (
                    <p className="font-mono text-xs text-muted-foreground">
                      LLM call {compactId(condition.llm_call_id)}
                    </p>
                  ) : null}
                </section>

                <Separator />

                <section className="grid gap-3">
                  <SectionHeading icon={BookOpenText} label="Sources" />
                  <SourceBlock title="Exact clause" source={condition.provenance} />
                  <SourceBlock title="Surrounding context" source={condition.source_context} />
                </section>

                <Separator />

                <section className="grid gap-3">
                  <SectionHeading icon={GitBranch} label="Cross references" />
                  {condition.cross_refs.length > 0 ? (
                    <div className="grid gap-3">
                      {condition.cross_refs.map((crossRef) => (
                        <div
                          key={`${condition.id}-${crossRef.to_label}`}
                          className="rounded-md border bg-muted/20 p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={crossRef.resolved ? "secondary" : "outline"}>
                              Section {crossRef.to_label}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {crossRef.resolved ? "Resolved" : "Unresolved"}
                            </span>
                          </div>
                          {crossRef.source ? (
                            <p className="mt-3 text-sm leading-6 text-muted-foreground">
                              {crossRef.source.text}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No section cross references were detected for this condition.
                    </p>
                  )}
                </section>

                <Separator />

                <section className="grid gap-2 text-xs text-muted-foreground">
                  <p className="font-mono">Condition {condition.id}</p>
                  <p className="font-mono">Segment {condition.segment_id}</p>
                  {condition.dependencies.length > 0 ? (
                    <p className="font-mono">
                      Dependencies {condition.dependencies.map(compactId).join(", ")}
                    </p>
                  ) : null}
                </section>
              </div>
            </ScrollArea>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function SectionHeading({
  icon: Icon,
  label,
}: {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 text-sm font-medium">
      <Icon className="size-4 text-primary" aria-hidden="true" />
      <h3>{label}</h3>
    </div>
  );
}

function SourceBlock({ title, source }: { title: string; source: Provenance | null }) {
  if (!source) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {title}: unavailable
      </div>
    );
  }

  return (
    <div className="rounded-md border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{source.label ?? "Source"}</Badge>
        <span className="text-xs text-muted-foreground">
          {source.filename} / {source.char_start}-{source.char_end}
        </span>
      </div>
      {source.heading ? <p className="mt-3 text-sm font-medium">{source.heading}</p> : null}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
        {source.text}
      </p>
    </div>
  );
}
