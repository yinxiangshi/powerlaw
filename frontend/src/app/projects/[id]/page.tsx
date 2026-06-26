import Link from "next/link";
import { notFound } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Files,
  GitBranch,
  History,
  ListChecks,
  Network,
  UsersRound,
} from "lucide-react";

import { AuditHistory, DocumentFilesTable } from "@/components/audit-log";
import { ConditionsWorkspace } from "@/components/conditions-workspace";
import { EmptyState } from "@/components/empty-state";
import { ProjectGraph } from "@/components/project-graph";
import { StatusBadge } from "@/components/status-badge";
import { UploadDocumentsForm } from "@/components/upload-documents-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  compactId,
  formatDate,
  formatPercent,
  pluralize,
  titleize,
} from "@/lib/format";
import {
  getDefinedTerms,
  getProject,
  getProjectConditions,
  getProjectDocuments,
  getProjectEvents,
  getProjectParties,
  getReviewQueue,
  type AuditEvent,
  type Condition,
  type DefinedTerm,
  type DocumentRecord,
  type Party,
  type ProjectDetail,
  type ReviewItem,
} from "@/lib/powerlaw-api";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await loadProjectWorkspace(id);

  if (data.notFound) {
    notFound();
  }

  if (data.error || !data.project) {
    return (
      <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <Alert variant="destructive">
            <AlertTriangle className="size-4" aria-hidden="true" />
            <AlertTitle>Project unavailable</AlertTitle>
            <AlertDescription>{data.error ?? "The project could not be loaded."}</AlertDescription>
          </Alert>
        </div>
      </main>
    );
  }

  const { project, documents, conditions, parties, reviewQueue, definedTerms, events } = data;
  const confirmed = conditions.filter(
    (condition) => condition.verification_status === "lawyer_confirmed"
  ).length;
  const discretionary = conditions.filter((condition) => condition.discretionary).length;
  const graphNodes =
    1 + documents.length + parties.length + conditions.length + definedTerms.length;
  const unresolvedTerms = definedTerms.reduce(
    (count, term) => count + term.members.filter((member) => !member.resolved).length,
    0
  );

  return (
    <main className="min-h-screen bg-background px-4 py-5 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-5">
        <header className="flex flex-col gap-4 border-b pb-5">
          <Link
            href="/"
            className={buttonVariants({ variant: "ghost", className: "w-fit px-0" })}
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Projects
          </Link>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-semibold tracking-normal sm:text-3xl">
                  {project.name}
                </h1>
                {project.aliases.map((alias) => (
                  <Badge key={alias} variant="secondary">
                    {alias}
                  </Badge>
                ))}
              </div>
              <p className="mt-2 font-mono text-sm text-muted-foreground">
                {compactId(project.id)} / updated {formatDate(project.updated_at)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 xl:justify-end">
              <StatusBadge value={project.counters.awaiting_review ? "unverified" : "done"} />
              <Badge variant="outline">
                {formatPercent(project.counters.percent_satisfied)} satisfied
              </Badge>
            </div>
          </div>
        </header>

        <Tabs
          defaultValue="files"
          orientation="vertical"
          className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]"
        >
          <aside className="lg:sticky lg:top-5 lg:self-start">
            <div className="rounded-lg border bg-card p-3 shadow-xs">
              <div className="px-2 py-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Workspace
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Navigate the project record.
                </p>
              </div>
              <TabsList className="mt-2 grid h-auto w-full grid-cols-2 gap-2 bg-transparent p-0 text-left md:grid-cols-4 lg:flex lg:flex-col">
                <WorkspaceNavItem
                  value="files"
                  label="Files"
                  detail="Uploaded records"
                  count={documents.length}
                  icon={Files}
                />
                <WorkspaceNavItem
                  value="conditions"
                  label="Conditions"
                  detail={`${confirmed} confirmed`}
                  count={conditions.length}
                  icon={ListChecks}
                />
                <WorkspaceNavItem
                  value="graph"
                  label="Graph"
                  detail="Whole project map"
                  count={graphNodes}
                  icon={GitBranch}
                />
                <WorkspaceNavItem
                  value="review"
                  label="Review"
                  detail="Flags and gaps"
                  count={reviewQueue.length + unresolvedTerms}
                  icon={AlertTriangle}
                />
                <WorkspaceNavItem
                  value="terms"
                  label="Terms"
                  detail="Defined bundles"
                  count={definedTerms.length}
                  icon={Network}
                />
                <WorkspaceNavItem
                  value="audit"
                  label="Audit"
                  detail="Project history"
                  count={events.length}
                  icon={History}
                />
              </TabsList>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-2 rounded-lg border bg-card p-3 shadow-xs lg:grid-cols-1">
              <SidebarMetric label="Discretionary" value={discretionary} />
              <SidebarMetric
                label="Awaiting review"
                value={project.counters.awaiting_review}
              />
              <SidebarMetric
                label="Satisfied"
                value={formatPercent(project.counters.percent_satisfied)}
              />
            </div>
          </aside>

          <section className="min-w-0">
            <TabsContent value="files" className="m-0 grid gap-4">
              <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="min-w-0">
                  <WorkspaceSectionHeader
                    title="Files"
                    detail={`${pluralize(documents.length, "document")} in the project workspace`}
                  />
                  <div className="mt-4">
                    <DocumentFilesTable documents={documents} events={events} />
                  </div>
                </div>
                <ProjectRail projectId={project.id} parties={parties} />
              </div>
            </TabsContent>

            <TabsContent value="conditions" className="m-0 grid gap-4">
              <WorkspaceSectionHeader
                title="Conditions"
                detail={`${pluralize(conditions.length, "checklist item")} extracted for review`}
              />
              <ConditionsWorkspace
                conditions={conditions}
                projectId={project.id}
                hasDocuments={documents.length > 0}
              />
            </TabsContent>

            <TabsContent value="graph" className="m-0 grid gap-4">
              <WorkspaceSectionHeader
                title="Graph"
                detail="Whole-project map of files, parties, terms, conditions, and dependencies"
              />
              <ProjectGraph
                project={project}
                documents={documents}
                conditions={conditions}
                parties={parties}
                definedTerms={definedTerms}
              />
            </TabsContent>

            <TabsContent value="review" className="m-0 grid gap-4">
              <WorkspaceSectionHeader
                title="Review"
                detail={`${pluralize(reviewQueue.length + unresolvedTerms, "item")} needs attention`}
              />
              <ReviewTable reviewQueue={reviewQueue} />
            </TabsContent>

            <TabsContent value="terms" className="m-0 grid gap-4">
              <WorkspaceSectionHeader
                title="Terms"
                detail={`${pluralize(definedTerms.length, "defined term")} available`}
              />
              <TermsTable definedTerms={definedTerms} />
            </TabsContent>

            <TabsContent value="audit" className="m-0 grid gap-4">
              <WorkspaceSectionHeader
                title="Audit"
                detail={`${pluralize(events.length, "event")} recorded for this project`}
              />
              <AuditHistory events={events} />
            </TabsContent>
          </section>
        </Tabs>
      </div>
    </main>
  );
}

function WorkspaceNavItem({
  value,
  label,
  detail,
  count,
  icon: Icon,
}: {
  value: string;
  label: string;
  detail: string;
  count: number;
  icon: LucideIcon;
}) {
  return (
    <TabsTrigger
      value={value}
      className="h-auto min-h-16 justify-start gap-3 rounded-md border bg-background/50 px-3 py-3 text-left data-active:border-primary/40 data-active:bg-primary/10 data-active:text-foreground lg:w-full"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-primary">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col items-start">
        <span className="text-sm font-medium">{label}</span>
        <span className="mt-0.5 line-clamp-1 text-xs font-normal text-muted-foreground">
          {detail}
        </span>
      </span>
      <span className="ml-auto font-mono text-xs text-muted-foreground">{count}</span>
    </TabsTrigger>
  );
}

function SidebarMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-muted/50 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-lg text-foreground">{value}</p>
    </div>
  );
}

function WorkspaceSectionHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex flex-col gap-1 border-b pb-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

function ProjectRail({ projectId, parties }: { projectId: string; parties: Party[] }) {
  return (
    <aside className="flex flex-col gap-5 xl:sticky xl:top-5 xl:self-start">
      <Card>
        <CardHeader>
          <CardTitle>Upload files</CardTitle>
          <CardDescription>Add documents to this matter.</CardDescription>
        </CardHeader>
        <CardContent>
          <UploadDocumentsForm projectId={projectId} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parties</CardTitle>
          <CardDescription>{pluralize(parties.length, "party")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {parties.length > 0 ? (
            parties.map((party) => (
              <div key={party.id} className="rounded-md border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium">{party.canonical_name}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {titleize(party.entity_type)}
                    </p>
                  </div>
                  <UsersRound className="mt-1 size-4 shrink-0 text-primary" />
                </div>
                {party.aliases.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {party.aliases.slice(0, 4).map((alias) => (
                      <Badge key={alias} variant="outline">
                        {alias}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <EmptyState
              icon={UsersRound}
              title="No parties"
              detail="No parties have been identified for this project."
            />
          )}
        </CardContent>
      </Card>
    </aside>
  );
}

function ReviewTable({ reviewQueue }: { reviewQueue: ReviewItem[] }) {
  if (reviewQueue.length === 0) {
    return (
      <EmptyState icon={CheckCircle2} title="No review flags" detail="All current flags are clear." />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
      <Table className="min-w-[640px]">
        <TableHeader>
          <TableRow>
            <TableHead>Flag</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Opened</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reviewQueue.map((item) => (
            <TableRow key={item.event_id}>
              <TableCell className="whitespace-normal">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-review" />
                  <span>{item.reason ?? "Review required"}</span>
                </div>
              </TableCell>
              <TableCell>
                <span className="font-mono text-xs">
                  {item.target_id ? compactId(item.target_id) : titleize(item.target_type)}
                </span>
              </TableCell>
              <TableCell>{formatDate(item.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function TermsTable({ definedTerms }: { definedTerms: DefinedTerm[] }) {
  const termsWithMembers = definedTerms.filter((term) => term.members.length > 0);

  if (termsWithMembers.length === 0) {
    return (
      <EmptyState
        icon={Network}
        title="No bundles"
        detail="No defined-term bundles are available yet."
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
      <Table className="min-w-[680px]">
        <TableHeader>
          <TableRow>
            <TableHead>Term</TableHead>
            <TableHead>Members</TableHead>
            <TableHead>Resolved</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {termsWithMembers.map((term) => {
            const resolved = term.members.filter((member) => member.resolved).length;

            return (
              <TableRow key={term.id}>
                <TableCell className="font-medium">{term.term}</TableCell>
                <TableCell className="whitespace-normal">
                  <div className="flex flex-wrap gap-1.5">
                    {term.members.slice(0, 8).map((member) => (
                      <Badge
                        key={member.member_name}
                        variant={member.resolved ? "secondary" : "outline"}
                      >
                        {member.member_name}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="font-mono">
                  {resolved}/{term.members.length}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

async function loadProjectWorkspace(id: string): Promise<{
  project: ProjectDetail | null;
  documents: DocumentRecord[];
  conditions: Condition[];
  parties: Party[];
  reviewQueue: ReviewItem[];
  definedTerms: DefinedTerm[];
  events: AuditEvent[];
  error: string | null;
  notFound: boolean;
}> {
  try {
    const [project, documents, conditions, parties, reviewQueue, definedTerms, events] =
      await Promise.all([
        getProject(id),
        getProjectDocuments(id),
        getProjectConditions(id),
        getProjectParties(id),
        getReviewQueue(id),
        getDefinedTerms(id),
        getProjectEvents(id),
      ]);

    return {
      project,
      documents,
      conditions,
      parties,
      reviewQueue,
      definedTerms,
      events,
      error: null,
      notFound: false,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not load project.";
    return {
      project: null,
      documents: [],
      conditions: [],
      parties: [],
      reviewQueue: [],
      definedTerms: [],
      events: [],
      error: message,
      notFound: message.includes("404"),
    };
  }
}
