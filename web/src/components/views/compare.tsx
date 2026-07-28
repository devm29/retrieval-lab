"use client";

import { ArrowRight, GitCompareArrows, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { EmptyState, ErrorState, TableSkeleton } from "@/components/metrics/states";
import { Page, Section } from "@/components/shell/page";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CompareResult, MetricKey, Run } from "@/lib/api/schemas";
import { useCompare, useRuns } from "@/lib/api/queries";
import { METRICS, ago, blockingDrift, configLabel, score, shortId, signed } from "@/lib/format";
import { cn } from "@/lib/utils";

function pickBaseline(runs: Run[], candidate: Run | undefined): string | null {
  if (!candidate) return null;
  const sameConfig = runs.filter((r) => r.config.name === candidate.config.name && r.id !== candidate.id);
  return (sameConfig.find((r) => r.is_baseline) ?? sameConfig[0] ?? runs.find((r) => r.id !== candidate.id))?.id ?? null;
}

export function CompareView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const runs = useRuns({ page: 1 }, 100);
  const completed = (runs.data?.items ?? []).filter((r) => r.status === "completed" && r.mode === "full");
  const candidateId = params.get("candidate") ?? completed[0]?.id ?? null;
  const candidate = completed.find((r) => r.id === candidateId);
  const baselineId = params.get("baseline") ?? pickBaseline(completed, candidate);
  const comparison = useCompare(baselineId, candidateId);

  const setParam = (key: "baseline" | "candidate", value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    if (key === "candidate" && !params.get("baseline") && baselineId) next.set("baseline", baselineId);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  return (
    <Page title="Compare" subtitle="Diff two runs metric by metric and question by question, exactly as the CI gate does.">
      <div className="mb-8 grid items-end gap-4 rounded-xl bg-card p-5 shadow-xs ring-1 ring-border/70 md:grid-cols-[1fr_auto_1fr]">
        <RunPicker id="baseline" label="Baseline" runs={completed} value={baselineId} onChange={(v) => setParam("baseline", v)} />
        <ArrowRight className="mb-2.5 hidden size-4 text-muted-foreground md:block" aria-hidden />
        <RunPicker id="candidate" label="Candidate" runs={completed} value={candidateId} onChange={(v) => setParam("candidate", v)} />
      </div>

      {runs.isPending || comparison.isPending ? (
        baselineId && candidateId ? <TableSkeleton rows={8} /> : null
      ) : null}
      {comparison.isError ? <ErrorState error={comparison.error} /> : null}
      {!runs.isPending && completed.length < 2 ? (
        <EmptyState
          icon={GitCompareArrows}
          title="Two completed runs are needed"
          description="Run at least two evaluations, then pick a baseline and a candidate."
        />
      ) : null}
      {comparison.data ? <Comparison data={comparison.data} /> : null}
    </Page>
  );
}

function RunPicker({
  id,
  label,
  runs,
  value,
  onChange,
}: {
  id: string;
  label: string;
  runs: Run[];
  value: string | null;
  onChange: (value: string) => void;
}) {
  return (
    <div className="min-w-0 space-y-2">
      <Label htmlFor={id} className="text-[13px] font-medium">
        {label}
      </Label>
      <Select value={value ?? ""} onValueChange={onChange}>
        <SelectTrigger id={id} className="h-9 w-full rounded-lg">
          <SelectValue placeholder="Choose a run" />
        </SelectTrigger>
        <SelectContent>
          {runs.map((run) => (
            <SelectItem key={run.id} value={run.id}>
              {configLabel(run.config)} · {run.label ?? shortId(run.id)} · {ago(run.finished_at)}
              {run.is_baseline ? " · baseline" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function GateVerdict({ gate }: { gate: CompareResult["gate"] }) {
  const drift = blockingDrift(gate);
  if (drift) {
    return (
      <div role="status" className="flex items-center gap-3 rounded-xl bg-warning/10 p-4 ring-1 ring-warning/30">
        <ShieldAlert className="size-6 shrink-0 text-warning" strokeWidth={1.75} aria-hidden />
        <div>
          <p className="text-[15px] font-semibold">These runs are not comparable</p>
          <p className="text-[13px] text-muted-foreground">
            {drift} changed between the two runs, so the gate would refuse this diff rather than pass or fail it.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-3 rounded-xl p-4 ring-1",
        gate.passed ? "bg-success/8 ring-success/25" : "bg-destructive/8 ring-destructive/25",
      )}
    >
      {gate.passed ? (
        <ShieldCheck className="size-6 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
      ) : (
        <ShieldAlert className="size-6 shrink-0 text-destructive" strokeWidth={1.75} aria-hidden />
      )}
      <div>
        <p className="text-[15px] font-semibold">{gate.passed ? "The candidate would pass the gate" : "The candidate would fail the gate"}</p>
        <p className="text-[13px] text-muted-foreground">
          Tolerance: nDCG −{gate.tolerance.ndcg_at_k}, faithfulness −{gate.tolerance.faithfulness} (absolute)
        </p>
      </div>
    </div>
  );
}

function Comparison({ data }: { data: CompareResult }) {
  const { gate } = data;
  const maxDelta = Math.max(0.05, ...data.questions.map((q) => Math.abs(q.delta ?? 0)));
  const changed = data.questions.filter((q) => q.delta !== null && Math.abs(q.delta) > 1e-6);

  return (
    <div className="space-y-10">
      <GateVerdict gate={gate} />

      <Section title="Metrics">
        <div className="overflow-x-auto rounded-xl bg-card shadow-xs ring-1 ring-border/70">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="text-[12px] text-muted-foreground">
                <th className="py-2.5 pl-4 text-left font-medium">Metric</th>
                <th className="py-2.5 text-right font-medium">Baseline</th>
                <th className="py-2.5 text-right font-medium">Candidate</th>
                <th className="py-2.5 pr-4 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {gate.deltas.map((d) => {
                const info = METRICS[d.metric as MetricKey];
                const better = d.delta !== null && (info?.lowerIsBetter ? d.delta < 0 : d.delta > 0);
                return (
                  <tr key={d.metric} className="h-11 border-t border-border/60">
                    <td className="pl-4">
                      {info?.label ?? d.metric}
                      {d.tolerance !== null ? <span className="ml-2 text-[11px] text-muted-foreground">gated</span> : null}
                    </td>
                    <td className="text-right tabular-nums">{score(d.baseline)}</td>
                    <td className="text-right tabular-nums">{score(d.candidate)}</td>
                    <td
                      className={cn(
                        "pr-4 text-right font-medium tabular-nums",
                        d.regressed ? "text-destructive" : d.delta && Math.abs(d.delta) > 1e-6 ? (better ? "text-success" : "text-muted-foreground") : "text-muted-foreground",
                      )}
                    >
                      {signed(d.delta)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="Per-question nDCG change"
        description={`${changed.length} of ${data.questions.length} questions moved. Regressions first.`}
      >
        <div className="mb-2 flex gap-4 text-[12px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-sm bg-chart-2" /> Worse
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-sm bg-chart-1" /> Better
          </span>
        </div>
        {changed.length === 0 ? (
          <p className="rounded-xl bg-card p-5 text-[14px] text-muted-foreground ring-1 ring-border/70">
            Every question scored the same in both runs.
          </p>
        ) : (
          <ul className="divide-y divide-border/60 rounded-xl bg-card shadow-xs ring-1 ring-border/70">
            {changed.map((q) => {
              const delta = q.delta ?? 0;
              const width = (Math.abs(delta) / maxDelta) * 50;
              return (
                <li key={q.question_id} className="grid min-h-11 grid-cols-[1fr_200px_64px] items-center gap-4 px-4 py-2">
                  <Link
                    href={`/runs/${data.candidate.id}/questions/${q.question_id}`}
                    className="line-clamp-1 text-[13px] outline-none hover:underline focus-visible:underline"
                  >
                    {q.question}
                  </Link>
                  <div className="relative h-2 rounded-full bg-secondary" aria-hidden>
                    <span className="absolute top-0 left-1/2 h-2 w-px bg-border" />
                    <span
                      className={cn("absolute top-0 h-2 rounded-full", delta < 0 ? "bg-chart-2" : "bg-chart-1")}
                      style={delta < 0 ? { right: "50%", width: `${width}%` } : { left: "50%", width: `${width}%` }}
                    />
                  </div>
                  <span className="text-right text-[13px] font-medium tabular-nums">{signed(q.delta, 2)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}
