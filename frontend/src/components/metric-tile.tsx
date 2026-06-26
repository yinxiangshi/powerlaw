import type { LucideIcon } from "lucide-react";

type MetricTileProps = {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
};

export function MetricTile({ label, value, detail, icon: Icon }: MetricTileProps) {
  return (
    <section className="rounded-lg border bg-card p-4 shadow-xs">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 font-mono text-3xl text-foreground">{value}</p>
        </div>
        <span className="flex size-9 items-center justify-center rounded-md bg-secondary text-primary">
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{detail}</p>
    </section>
  );
}

