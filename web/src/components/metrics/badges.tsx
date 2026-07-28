import { CheckCircle2, CircleDashed, Loader2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";

import type { GateResult, RunStatus } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

const BASE = "inline-flex h-5 items-center gap-1 rounded-full px-2 text-[11px] font-medium whitespace-nowrap";

export function StatusBadge({ status }: { status: RunStatus }) {
  switch (status) {
    case "completed":
      return (
        <span className={cn(BASE, "bg-success/15 text-success")}>
          <CheckCircle2 className="size-3" strokeWidth={2} aria-hidden />
          Completed
        </span>
      );
    case "running":
      return (
        <span className={cn(BASE, "bg-primary/12 text-primary")}>
          <Loader2 className="size-3 animate-spin motion-reduce:animate-none" strokeWidth={2} aria-hidden />
          Running
        </span>
      );
    case "queued":
      return (
        <span className={cn(BASE, "bg-secondary text-muted-foreground")}>
          <CircleDashed className="size-3" strokeWidth={2} aria-hidden />
          Queued
        </span>
      );
    case "failed":
      return (
        <span className={cn(BASE, "bg-destructive/12 text-destructive")}>
          <XCircle className="size-3" strokeWidth={2} aria-hidden />
          Failed
        </span>
      );
  }
}

export function GateBadge({ gate, isBaseline }: { gate: GateResult | null | undefined; isBaseline?: boolean }) {
  if (isBaseline) {
    return <span className={cn(BASE, "bg-primary/12 text-primary")}>Baseline</span>;
  }
  if (!gate) {
    return <span className={cn(BASE, "bg-secondary text-muted-foreground")}>No baseline</span>;
  }
  if (gate.drift.some((d) => d.blocking)) {
    return <span className={cn(BASE, "bg-warning/15 text-warning")}>Not comparable</span>;
  }
  return gate.passed ? (
    <span className={cn(BASE, "bg-success/15 text-success")}>
      <ShieldCheck className="size-3" strokeWidth={2} aria-hidden />
      Gate passed
    </span>
  ) : (
    <span className={cn(BASE, "bg-destructive/12 text-destructive")}>
      <ShieldAlert className="size-3" strokeWidth={2} aria-hidden />
      Regressed
    </span>
  );
}

export function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "blue" | "green" | "red" | "orange" }) {
  const tones = {
    neutral: "bg-secondary text-muted-foreground",
    blue: "bg-primary/12 text-primary",
    green: "bg-success/15 text-success",
    red: "bg-destructive/12 text-destructive",
    orange: "bg-warning/15 text-warning",
  } as const;
  return <span className={cn(BASE, tones[tone])}>{children}</span>;
}
