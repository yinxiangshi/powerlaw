import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BriefcaseBusiness,
  FileText,
  FolderKanban,
  ListChecks,
  ShieldCheck,
} from "lucide-react";

import { createProjectAction } from "@/app/actions";
import { DeleteProjectButton } from "@/components/delete-project-button";
import { EmptyState } from "@/components/empty-state";
import { MetricTile } from "@/components/metric-tile";
import { StatusBadge } from "@/components/status-badge";
import { SubmitButton } from "@/components/submit-button";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { compactId, formatPercent, pluralize } from "@/lib/format";
import { getProjects, type ProjectDetail } from "@/lib/powerlaw-api";

export default async function Home() {
  const { projects, error } = await loadProjects();
  const totals = projects.reduce(
    (acc, project) => {
      acc.documents += project.counters.documents_ingested;
      acc.conditions += project.counters.conditions_extracted;
      acc.review += project.counters.awaiting_review;
      return acc;
    },
    { documents: 0, conditions: 0, review: 0 }
  );

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <BriefcaseBusiness className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-medium text-muted-foreground">PowerLaw</p>
                <h1 className="text-3xl font-semibold">Project overview</h1>
              </div>
            </div>
          </div>
          <Badge variant="outline" className="w-fit font-mono">
            API {process.env.NEXT_PUBLIC_POWERLAW_API_BASE_URL ?? "localhost:8001"}
          </Badge>
        </header>

        {error ? (
          <Alert variant="destructive">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>Backend unavailable</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile
            label="Projects"
            value={projects.length}
            detail={pluralize(projects.length, "active matter")}
            icon={FolderKanban}
          />
          <MetricTile
            label="Files"
            value={totals.documents}
            detail="Available for review"
            icon={FileText}
          />
          <MetricTile
            label="Conditions"
            value={totals.conditions}
            detail="Linked to source text"
            icon={ListChecks}
          />
          <MetricTile
            label="Review"
            value={totals.review}
            detail="Awaiting reviewer decision"
            icon={ShieldCheck}
          />
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="min-w-0 rounded-lg border bg-card shadow-xs">
            <div className="flex flex-col gap-2 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Available projects</h2>
                <p className="text-sm text-muted-foreground">
                  {pluralize(projects.length, "project")}
                </p>
              </div>
            </div>

            {projects.length > 0 ? (
              <div className="overflow-x-auto">
                <Table className="min-w-[900px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Project</TableHead>
                      <TableHead>Files</TableHead>
                      <TableHead>Conditions</TableHead>
                      <TableHead>Review</TableHead>
                      <TableHead>Satisfied</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {projects.map((project) => (
                      <TableRow key={project.id}>
                        <TableCell className="whitespace-normal">
                          <div className="flex flex-col gap-1">
                            <Link
                              href={`/projects/${project.id}`}
                              className="font-medium text-foreground hover:text-primary"
                            >
                              {project.name}
                            </Link>
                            <span className="font-mono text-xs text-muted-foreground">
                              {compactId(project.id)}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="font-mono">
                          {project.counters.documents_ingested}
                        </TableCell>
                        <TableCell className="font-mono">
                          {project.counters.conditions_extracted}
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            value={
                              project.counters.awaiting_review > 0 ? "unverified" : "done"
                            }
                          />
                        </TableCell>
                        <TableCell className="font-mono">
                          {formatPercent(project.counters.percent_satisfied)}
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            <Link
                              href={`/projects/${project.id}`}
                              className={buttonVariants({ variant: "ghost", size: "sm" })}
                            >
                              <ArrowRight className="size-4" aria-hidden="true" />
                              Open
                            </Link>
                            <DeleteProjectButton
                              projectId={project.id}
                              projectName={project.name}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <div className="p-4">
                <EmptyState
                  icon={FolderKanban}
                  title="No projects"
                  detail="Create a project to start collecting documents and review items."
                />
              </div>
            )}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Create project</CardTitle>
              <CardDescription>Set up a matter workspace.</CardDescription>
            </CardHeader>
            <CardContent>
              <form action={createProjectAction} className="flex flex-col gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">Name</Label>
                  <Input id="name" name="name" placeholder="NC-31 Solar Financing" required />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="aliases">Aliases</Label>
                  <Input id="aliases" name="aliases" placeholder="NC-31, Bladenboro" />
                </div>
                <Separator />
                <SubmitButton pendingText="Creating" icon="plus">
                  Create project
                </SubmitButton>
              </form>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}

async function loadProjects(): Promise<{ projects: ProjectDetail[]; error: string | null }> {
  try {
    return { projects: await getProjects(), error: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not load projects.";
    return { projects: [], error: message };
  }
}
