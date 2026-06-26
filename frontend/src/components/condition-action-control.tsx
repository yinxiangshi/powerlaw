"use client";

import { Bell, RefreshCw, OctagonMinus } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState, useTransition } from "react";

import { logConditionActionSelectionAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ConditionActionStatus } from "@/lib/powerlaw-api";

type ConditionActionChoice = Exclude<ConditionActionStatus, "none">;

const actionOptions = [
  { value: "remind", label: "Remind", icon: Bell },
  { value: "stop", label: "Stop", icon: OctagonMinus },
  { value: "refresh", label: "Refresh", icon: RefreshCw },
] satisfies Array<{
  value: ConditionActionChoice;
  label: string;
  icon: LucideIcon;
}>;

export function ConditionActionControl({ conditionId }: { conditionId: string }) {
  const [selected, setSelected] = useState<ConditionActionStatus>("none");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  return (
    <div className="grid gap-1">
      <TooltipProvider>
        <div className="flex items-center gap-1">
          {actionOptions.map((option) => {
            const Icon = option.icon;
            const isSelected = selected === option.value;

            return (
              <Tooltip key={option.value}>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      size="icon-sm"
                      variant={isSelected ? "default" : "outline"}
                      aria-label={option.label}
                      aria-pressed={isSelected}
                      disabled={isPending}
                      onClick={() => {
                        const previous = selected;
                        setSelected(option.value);
                        setError(null);
                        startTransition(async () => {
                          try {
                            await logConditionActionSelectionAction(
                              conditionId,
                              previous,
                              option.value
                            );
                          } catch (caught) {
                            setSelected(previous);
                            setError(
                              caught instanceof Error ? caught.message : "Action log failed."
                            );
                          }
                        });
                      }}
                    >
                      <Icon className="size-3.5" aria-hidden="true" />
                    </Button>
                  }
                />
                <TooltipContent>{option.label}</TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </TooltipProvider>
      {error ? <p className="max-w-36 text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
