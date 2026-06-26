"use client";

import * as d3 from "d3";
import { FileText, GitBranch, Network, Scale, UsersRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { compactId, pluralize, titleize } from "@/lib/format";
import type {
  Condition,
  DefinedTerm,
  DocumentRecord,
  Party,
  ProjectDetail,
} from "@/lib/powerlaw-api";

type NodeKind = "project" | "document" | "party" | "condition" | "term";
type LinkKind =
  | "project"
  | "document"
  | "party"
  | "term"
  | "dependency"
  | "reference";

type GraphNode = d3.SimulationNodeDatum & {
  id: string;
  kind: NodeKind;
  label: string;
  title: string;
  detail: string;
  status: string | null;
  source: string | null;
  incoming: number;
  outgoing: number;
  color: string;
  radius: number;
};

type GraphLink = {
  id: string;
  sourceId: string;
  targetId: string;
  kind: LinkKind;
  label: string;
  color: string;
  dashed: boolean;
};

type LayoutGraphNode = GraphNode & {
  x: number;
  y: number;
};

type RenderedGraphLink = GraphLink &
  d3.SimulationLinkDatum<LayoutGraphNode> & {
    source: LayoutGraphNode;
    target: LayoutGraphNode;
  };

const KIND_STYLES: Record<NodeKind, { color: string; radius: number }> = {
  project: { color: "#1f6f73", radius: 34 },
  document: { color: "#3b6ea8", radius: 24 },
  party: { color: "#7a5a9e", radius: 23 },
  condition: { color: "#9a6a20", radius: 21 },
  term: { color: "#427f58", radius: 20 },
};

const STATUS_COLORS: Record<string, string> = {
  open: "#9a6a20",
  ongoing: "#b7791f",
  waived: "#786f8f",
  verified: "#2f855a",
};

const LINK_STYLES: Record<LinkKind, { color: string; dashed: boolean }> = {
  project: { color: "#1f6f73", dashed: false },
  document: { color: "#3b6ea8", dashed: false },
  party: { color: "#7a5a9e", dashed: false },
  term: { color: "#427f58", dashed: false },
  dependency: { color: "#b7791f", dashed: false },
  reference: { color: "#786f8f", dashed: true },
};

export function ProjectGraph({
  project,
  documents,
  conditions,
  parties,
  definedTerms,
}: {
  project: ProjectDetail;
  documents: DocumentRecord[];
  conditions: Condition[];
  parties: Party[];
  definedTerms: DefinedTerm[];
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 960, height: 660 });
  const { nodes, links, totals } = useMemo(
    () => buildProjectGraph({ project, documents, conditions, parties, definedTerms }),
    [project, documents, conditions, parties, definedTerms]
  );
  const [selectedId, setSelectedId] = useState<string | null>(nodes[0]?.id ?? null);
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0] ?? null;

  useEffect(() => {
    if (!frameRef.current) return;

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const width = Math.max(320, Math.floor(entry.contentRect.width));
      setSize({ width, height: width < 760 ? 560 : 680 });
    });
    observer.observe(frameRef.current);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const width = size.width;
    const height = size.height;
    const renderedNodes = seedNodes(nodes, width, height);
    const nodeById = new Map(renderedNodes.map((node) => [node.id, node]));
    const renderedLinks: RenderedGraphLink[] = links.flatMap((link) => {
      const source = nodeById.get(link.sourceId);
      const target = nodeById.get(link.targetId);
      return source && target ? [{ ...link, source, target }] : [];
    });

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img");

    const defs = svg.append("defs");
    for (const [kind, style] of Object.entries(LINK_STYLES) as Array<
      [LinkKind, (typeof LINK_STYLES)[LinkKind]]
    >) {
      defs
        .append("marker")
        .attr("id", `project-graph-arrow-${kind}`)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 26)
        .attr("refY", 0)
        .attr("markerWidth", 6.5)
        .attr("markerHeight", 6.5)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", style.color);
    }

    const field = svg.append("g");
    const link = field
      .append("g")
      .attr("fill", "none")
      .selectAll<SVGPathElement, RenderedGraphLink>("path")
      .data(renderedLinks)
      .join("path")
      .attr("stroke", (d) => d.color)
      .attr("stroke-width", (d) => (d.kind === "dependency" ? 2.2 : 1.4))
      .attr("stroke-dasharray", (d) => (d.dashed ? "5 5" : null))
      .attr("stroke-opacity", (d) => (d.kind === "project" ? 0.32 : 0.56))
      .attr("marker-end", (d) => `url(#project-graph-arrow-${d.kind})`);

    const node = field
      .append("g")
      .selectAll<SVGGElement, LayoutGraphNode>("g")
      .data(renderedNodes)
      .join("g")
      .attr("tabindex", 0)
      .attr("class", "cursor-pointer outline-none")
      .on("click", (_, d) => setSelectedId(d.id))
      .on("keydown", (event: KeyboardEvent, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setSelectedId(d.id);
        }
      });

    node
      .append("circle")
      .attr("r", (d) => d.radius + 10)
      .attr("fill", "transparent")
      .attr("stroke", (d) => d.color)
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.18);

    node
      .append("circle")
      .attr("r", (d) => d.radius)
      .attr("fill", (d) => d.color)
      .attr("fill-opacity", 0.94)
      .attr("stroke", "#f8fafc")
      .attr("stroke-width", 2.5);

    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", "#ffffff")
      .attr("font-size", (d) => (d.kind === "project" ? 12 : 10))
      .attr("font-weight", 800)
      .text((d) => shortLabel(d.label, d.kind === "project" ? 12 : 8));

    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => d.radius + 18)
      .attr("fill", "#334155")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .text((d) => titleize(d.kind));

    node.append("title").text((d) => `${titleize(d.kind)}: ${d.title}`);

    const simulation = d3
      .forceSimulation<LayoutGraphNode>(renderedNodes)
      .force(
        "link",
        d3
          .forceLink<LayoutGraphNode, RenderedGraphLink>(renderedLinks)
          .id((d) => d.id)
          .distance((d) => linkDistance(d.kind))
          .strength((d) => linkStrength(d.kind))
      )
      .force(
        "charge",
        d3.forceManyBody<LayoutGraphNode>().strength((d) => (d.kind === "project" ? -1250 : -520))
      )
      .force("collide", d3.forceCollide<LayoutGraphNode>().radius((d) => d.radius + 34))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("x", d3.forceX<LayoutGraphNode>((d) => layerX(d.kind, width)).strength(0.08))
      .force("y", d3.forceY<LayoutGraphNode>(height / 2).strength(0.045));

    const drag = d3
      .drag<SVGGElement, LayoutGraphNode>()
      .on("start", (event, d) => {
        if (!event.active) simulation.alphaTarget(0.2).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    node.call(drag);

    simulation.on("tick", () => {
      link.attr("d", (d) => {
        const source = d.source as LayoutGraphNode;
        const target = d.target as LayoutGraphNode;
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const curve = Math.sqrt(dx * dx + dy * dy) * (d.kind === "dependency" ? 0.2 : 0.1);
        return `M${source.x},${source.y} Q${source.x + dx / 2},${
          source.y + dy / 2 - curve
        } ${target.x},${target.y}`;
      });

      node.attr("transform", (d) => {
        d.x = clamp(d.x, 48, width - 48);
        d.y = clamp(d.y, 48, height - 62);
        return `translate(${d.x},${d.y})`;
      });
    });

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.55, 2.2])
      .on("zoom", (event) => {
        field.attr("transform", event.transform.toString());
      });
    svg.call(zoom);

    return () => {
      simulation.stop();
      svg.on(".zoom", null);
    };
  }, [links, nodes, size]);

  if (nodes.length <= 1) {
    return (
      <EmptyState
        icon={Network}
        title="No project graph"
        detail="Upload project files to populate the project graph."
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 overflow-hidden rounded-lg border bg-card shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div>
            <p className="text-sm font-medium">Project graph</p>
            <p className="text-xs text-muted-foreground">
              Files, parties, terms, conditions, and dependency links in one matter map.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <GraphKey color={LINK_STYLES.document.color} label="Extracted from file" />
            <GraphKey color={LINK_STYLES.party.color} label="Party role" />
            <GraphKey color={LINK_STYLES.dependency.color} label="Condition dependency" />
            <GraphKey color={LINK_STYLES.reference.color} label="Cross reference" dashed />
          </div>
        </div>
        <div ref={frameRef} className="h-[560px] w-full bg-muted/30 xl:h-[680px]">
          <svg ref={svgRef} className="h-full w-full" aria-label="Whole project graph" />
        </div>
      </div>

      <aside className="min-w-0 rounded-lg border bg-card p-4 shadow-xs xl:sticky xl:top-5 xl:self-start">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Graph summary</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {pluralize(nodes.length, "node")} / {pluralize(links.length, "link")}
            </p>
          </div>
          <GitBranch className="mt-0.5 size-4 text-primary" aria-hidden="true" />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <GraphMetric icon={FileText} label="Files" value={totals.documents} />
          <GraphMetric icon={UsersRound} label="Parties" value={totals.parties} />
          <GraphMetric icon={Scale} label="Conditions" value={totals.conditions} />
          <GraphMetric icon={Network} label="Terms" value={totals.terms} />
        </div>

        {selected ? (
          <div className="mt-5 border-t pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{titleize(selected.kind)}</Badge>
              {selected.status ? <StatusBadge value={selected.status} /> : null}
            </div>
            <p className="mt-3 text-sm font-medium leading-6">{selected.title}</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{selected.detail}</p>
            <dl className="mt-4 grid gap-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Links</dt>
                <dd>
                  {selected.incoming} inbound / {selected.outgoing} outbound
                </dd>
              </div>
              {selected.source ? (
                <div>
                  <dt className="text-xs text-muted-foreground">Source</dt>
                  <dd className="font-mono text-xs">{selected.source}</dd>
                </div>
              ) : null}
              <div>
                <dt className="text-xs text-muted-foreground">ID</dt>
                <dd className="font-mono text-xs">{compactId(stripKind(selected.id))}</dd>
              </div>
            </dl>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

function buildProjectGraph({
  project,
  documents,
  conditions,
  parties,
  definedTerms,
}: {
  project: ProjectDetail;
  documents: DocumentRecord[];
  conditions: Condition[];
  parties: Party[];
  definedTerms: DefinedTerm[];
}) {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const seenLinks = new Set<string>();
  const documentNodeById = new Map<string, string>();
  const partyNodeById = new Map<string, string>();
  const conditionNodeById = new Map<string, string>();
  const conditionBySegment = new Map<string, string>();

  const projectNodeId = graphId("project", project.id);
  nodes.push(makeNode(projectNodeId, "project", project.name, "Project record", null, null));

  for (const document of documents) {
    const nodeId = graphId("document", document.id);
    documentNodeById.set(document.id, nodeId);
    nodes.push(
      makeNode(
        nodeId,
        "document",
        document.title ?? document.filename,
        `${titleize(document.type)} / ${document.filename}`,
        document.status,
        document.filename
      )
    );
    addLink(links, seenLinks, projectNodeId, nodeId, "project", "contains");
  }

  for (const party of parties) {
    const nodeId = graphId("party", party.id);
    partyNodeById.set(party.id, nodeId);
    nodes.push(
      makeNode(
        nodeId,
        "party",
        party.canonical_name,
        `${titleize(party.entity_type)} / ${pluralize(party.roles.length, "role")}`,
        null,
        party.aliases.slice(0, 3).join(", ") || null
      )
    );
    addLink(links, seenLinks, projectNodeId, nodeId, "project", "project party");
    for (const role of party.roles) {
      const documentNode = documentNodeById.get(role.document_id);
      if (documentNode) addLink(links, seenLinks, documentNode, nodeId, "party", role.role);
    }
  }

  for (const condition of conditions) {
    const nodeId = graphId("condition", condition.id);
    conditionNodeById.set(condition.id, nodeId);
    conditionBySegment.set(condition.segment_id, nodeId);
    nodes.push(
      makeNode(
        nodeId,
        "condition",
        condition.provenance?.label ?? compactId(condition.id),
        condition.requirement_text,
        condition.status,
        condition.provenance
          ? `${condition.provenance.filename} / ${condition.provenance.label ?? "section"}`
          : null
      )
    );

    const documentNode = condition.provenance
      ? documentNodeById.get(condition.provenance.document_id)
      : null;
    addLink(
      links,
      seenLinks,
      documentNode ?? projectNodeId,
      nodeId,
      documentNode ? "document" : "project",
      "condition source"
    );

    const beneficiary = condition.beneficiary_party
      ? partyNodeById.get(condition.beneficiary_party)
      : null;
    if (beneficiary) addLink(links, seenLinks, beneficiary, nodeId, "party", "benefits");

    const obligor = condition.obligor_party ? partyNodeById.get(condition.obligor_party) : null;
    if (obligor) addLink(links, seenLinks, obligor, nodeId, "party", "obligated");
  }

  for (const term of definedTerms) {
    const nodeId = graphId("term", term.id);
    nodes.push(
      makeNode(
        nodeId,
        "term",
        term.term,
        `${titleize(term.definition_kind)} / ${pluralize(term.members.length, "member")}`,
        null,
        null
      )
    );

    const documentNode = term.document_id ? documentNodeById.get(term.document_id) : null;
    addLink(
      links,
      seenLinks,
      documentNode ?? projectNodeId,
      nodeId,
      documentNode ? "term" : "project",
      "defines"
    );

    for (const member of term.members) {
      const memberDocument = member.member_document
        ? documentNodeById.get(member.member_document)
        : null;
      if (memberDocument) {
        addLink(links, seenLinks, nodeId, memberDocument, "term", member.member_name);
      }
      const memberParty = member.member_party ? partyNodeById.get(member.member_party) : null;
      if (memberParty) addLink(links, seenLinks, nodeId, memberParty, "term", member.member_name);
    }
  }

  for (const condition of conditions) {
    const conditionNode = conditionNodeById.get(condition.id);
    if (!conditionNode) continue;

    for (const dependencyId of condition.dependencies) {
      const dependencyNode = conditionNodeById.get(dependencyId);
      if (dependencyNode) {
        addLink(links, seenLinks, dependencyNode, conditionNode, "dependency", "depends on");
      }
    }

    for (const crossRef of condition.cross_refs) {
      if (!crossRef.to_segment) continue;
      const referencedCondition = conditionBySegment.get(crossRef.to_segment);
      if (referencedCondition && referencedCondition !== conditionNode) {
        addLink(
          links,
          seenLinks,
          referencedCondition,
          conditionNode,
          "reference",
          `Section ${crossRef.to_label}`
        );
      }
    }
  }

  const nodeMetrics = new Map(nodes.map((node) => [node.id, node]));
  for (const link of links) {
    const source = nodeMetrics.get(link.sourceId);
    const target = nodeMetrics.get(link.targetId);
    if (source) source.outgoing += 1;
    if (target) target.incoming += 1;
  }

  return {
    nodes,
    links,
    totals: {
      documents: documents.length,
      parties: parties.length,
      conditions: conditions.length,
      terms: definedTerms.length,
    },
  };
}

function makeNode(
  id: string,
  kind: NodeKind,
  title: string,
  detail: string,
  status: string | null | undefined,
  source: string | null
): GraphNode {
  const style = KIND_STYLES[kind];
  const color = kind === "condition" && status ? STATUS_COLORS[status] ?? style.color : style.color;

  return {
    id,
    kind,
    label: nodeLabel(kind, title),
    title,
    detail,
    status: status ?? null,
    source,
    incoming: 0,
    outgoing: 0,
    color,
    radius: style.radius,
  };
}

function addLink(
  links: GraphLink[],
  seen: Set<string>,
  sourceId: string,
  targetId: string,
  kind: LinkKind,
  label: string
) {
  const id = `${sourceId}->${targetId}:${kind}:${label}`;
  if (seen.has(id) || sourceId === targetId) return;
  const style = LINK_STYLES[kind];
  seen.add(id);
  links.push({
    id,
    sourceId,
    targetId,
    kind,
    label,
    color: style.color,
    dashed: style.dashed,
  });
}

function seedNodes(nodes: GraphNode[], width: number, height: number): LayoutGraphNode[] {
  const counts = new Map<NodeKind, number>();
  const totals = nodes.reduce(
    (acc, node) => acc.set(node.kind, (acc.get(node.kind) ?? 0) + 1),
    new Map<NodeKind, number>()
  );

  return nodes.map((node) => {
    const index = counts.get(node.kind) ?? 0;
    counts.set(node.kind, index + 1);
    const total = totals.get(node.kind) ?? 1;
    const y = total === 1 ? height / 2 : ((index + 1) / (total + 1)) * height;
    return {
      ...node,
      x: layerX(node.kind, width),
      y,
    };
  });
}

function layerX(kind: NodeKind, width: number) {
  const layers: Record<NodeKind, number> = {
    project: 0.1,
    document: 0.3,
    party: 0.48,
    term: 0.64,
    condition: 0.82,
  };
  return width * layers[kind];
}

function linkDistance(kind: LinkKind) {
  if (kind === "project") return 145;
  if (kind === "dependency") return 120;
  if (kind === "reference") return 105;
  return 135;
}

function linkStrength(kind: LinkKind) {
  if (kind === "project") return 0.42;
  if (kind === "dependency") return 0.68;
  if (kind === "reference") return 0.35;
  return 0.5;
}

function nodeLabel(kind: NodeKind, title: string) {
  if (kind === "project") return "Matter";
  if (kind === "condition") return title;
  return title.split(/\s+/).slice(0, 2).join(" ");
}

function graphId(kind: NodeKind, id: string) {
  return `${kind}:${id}`;
}

function stripKind(id: string) {
  return id.includes(":") ? id.split(":").slice(1).join(":") : id;
}

function shortLabel(value: string, max: number) {
  return value.length <= max ? value : `${value.slice(0, max - 1)}...`;
}

function GraphKey({
  color,
  label,
  dashed = false,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-md border bg-background px-2.5 py-1 text-xs text-muted-foreground">
      <span
        className="h-px w-6"
        style={{
          backgroundImage: dashed
            ? `linear-gradient(to right, ${color} 50%, transparent 50%)`
            : undefined,
          backgroundSize: dashed ? "8px 1px" : undefined,
          backgroundColor: dashed ? undefined : color,
        }}
      />
      {label}
    </span>
  );
}

function GraphMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-md bg-muted/50 p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </div>
      <p className="mt-1 font-mono text-lg">{value}</p>
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
