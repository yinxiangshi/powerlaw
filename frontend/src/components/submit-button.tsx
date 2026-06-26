"use client";

import type { ComponentProps, ReactNode } from "react";
import { useFormStatus } from "react-dom";
import type { LucideIcon } from "lucide-react";
import { FileUp, ListChecks, Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";

type SubmitIcon = "file-up" | "list-checks" | "plus";

const icons = {
  "file-up": FileUp,
  "list-checks": ListChecks,
  plus: Plus,
} satisfies Record<SubmitIcon, LucideIcon>;

type SubmitButtonProps = {
  children: ReactNode;
  pendingText: string;
  icon?: SubmitIcon;
  className?: string;
  variant?: ComponentProps<typeof Button>["variant"];
};

export function SubmitButton({
  children,
  pendingText,
  icon,
  className,
  variant,
}: SubmitButtonProps) {
  const { pending } = useFormStatus();
  const Icon = icon ? icons[icon] : null;

  return (
    <Button type="submit" className={className} disabled={pending} variant={variant}>
      {pending ? (
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      ) : Icon ? (
        <Icon className="size-4" aria-hidden="true" />
      ) : null}
      {pending ? pendingText : children}
    </Button>
  );
}
