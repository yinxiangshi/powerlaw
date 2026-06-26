import { Badge } from "@/components/ui/badge";
import { titleize } from "@/lib/format";

export function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = value ?? "unknown";
  const variant =
    normalized === "error"
      ? "destructive"
      : normalized === "linked" ||
          normalized === "done" ||
          normalized === "lawyer_confirmed" ||
          normalized === "verified"
        ? "default"
        : normalized === "unverified" || normalized === "waived"
          ? "secondary"
          : "outline";

  return <Badge variant={variant}>{titleize(normalized)}</Badge>;
}
