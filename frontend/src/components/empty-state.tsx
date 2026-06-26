import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  detail,
}: {
  icon: LucideIcon;
  title: string;
  detail: string;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed bg-card/60 p-8 text-center">
      <span className="flex size-10 items-center justify-center rounded-md bg-secondary text-primary">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-medium">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

