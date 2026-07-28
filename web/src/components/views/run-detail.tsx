"use client";

import { CheckCircle2, ChevronRight, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Pill, StatusBadge } from "@/components/metrics/badges";
import { LatencyChart } from "@/components/metrics/charts";
import { KpiTile } from "@/components/metrics/kpi-tile";
import { Segmented } from "@/components/metrics/segmented";
import { ErrorState, TableSkeleton, TilesSkeleton } from "@/components/metrics/states";
import { Page, Section } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { GateResult, MetricKey, Run, RunSummary } from "@/lib/api/schemas";
import { type ResultSort, usePromoteBaseline, useRun, useRunGate, useRunResults } from "@/lib/api/queries";
import { GENERATION_METRICS, METRICS, RETRIEVAL_METRICS, STAGE_LABELS, ago, blockingDrift, configLabel, ms, percent, score, signed, usd } from "@/lib/format";

export function RunDetailView({ runId }: { runId: string }) {
  const run = useRun(runId);
  const completed = run.data?.status === "completed";
  const gate = useRunGate(runId, completed && run.data?.mode === "full");
  const promote = usePromoteBaseline();

  if (run.isError) {
    return (
      <Page title="Run" back={{ href: "/runs", label: "Runs" }}>
        <ErrorState error={run.error} onRetry={() => void run.refetch()} />
      </Page>
    );
  }
  if (!run.data) {
    return (
      <Page title="Run" back={{ href: "/runs", label: "Runs" }}>
        <TilesSkeleton />
      </Page>
    );
  }

  const data = run.data;
  const canPromote = completed && data.mode === "full" && !data.is_baseline;

  return (
    <Page
      title={configLabel(data.config)}
      back={{ href: "/runs", label: "Runs" }}
      subtitle={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusBadge status={data.status} />
          {data.is_baseline ? <Pill tone="blue">Baseline</Pill> : null}
          <span>
            {data.label ?? "Unlabelled run"} · {data.trigger} · {ago(data.created_at)} · k = {data.k}
          </span>
        </span>
      }
      actions={
        <>
          {completed ? (
            <Button variant="secondary" asChild>
              <Link href={`/compare?candidate=${data.id}`}>Compare</Link>
            </Button>
          ) : null}
          {canPromote ? (
            <Button
              onClick={() =>
                promote.mutate(data.id, {
                  onSuccess: () => toast.success(`This run is now the baseline for ${data.config.name}`),
                  onError: (e) => toast.error(e.message),
                })
              }
              disabled={promote.isPending}
            >
              Promote to baseline
            </Button>
          ) : null}
        </>
      }
    >
      {data.status === "queued" || data.status === "running" ? <RunProgress run={data} /> : null}
      {data.status === "failed" ? (
        <ErrorState title="This run failed" error={new Error(data.error ?? "No error was recorded.")} />
      ) : null}
      {data.summary ? (
        <div className="space-y-10">
          <MetricGrid summary={data.summary} gate={gate.data} />
          {gate.data && !data.is_baseline ? <GateCard gate={gate.data} /> : null}
          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Latency by stage</CardTitle>
                <CardDescription>
                  Per question across {data.summary.question_count} questions. BM25 and dense run in parallel.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <LatencyChart summary={data.summary} />
              </CardContent>
            </Card>
            <CostCard summary={data.summary} run={data} />
          </div>
          <QuestionTable run={data} />
        </div>
      ) : null}
    </Page>
  );
}

function RunProgress({ run }: { run: Run }) {
  const value = run.question_count ? (run.completed_count / run.question_count) * 100 : 0;
  return (
    <Card className="mb-8" aria-live="polite">
      <CardHeader>
        <CardTitle>{run.status === "queued" ? "Waiting to start" : "Scoring questions"}</CardTitle>
        <CardDescription className="tabular-nums">
          {run.completed_count} of {run.question_count} questions done
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Progress value={value} aria-label="Run progress" className="h-1.5" />
      </CardContent>
    </Card>
  );
}

function deltaFor(gate: GateResult | undefined, metric: MetricKey) {
  const delta = gate?.deltas.find((d) => d.metric === metric)?.delta;
  if (delta === null || delta === undefined) return null;
  return { value: delta, text: `${signed(delta)} vs baseline`, lowerIsBetter: METRICS[metric].lowerIsBetter ?? false };
}

const PERCENT_METRICS: ReadonlySet<MetricKey> = new Set([
  "faithfulness",
  "abstention_accuracy",
  "citation_accuracy",
  "false_abstention_rate",
]);

function MetricGrid({ summary, gate }: { summary: RunSummary; gate: GateResult | undefined }) {
  const groups: { title: string; metrics: MetricKey[] }[] = [
    { title: "Retrieval", metrics: RETRIEVAL_METRICS },
    ...(summary.mode === "full" ? [{ title: "Answers", metrics: GENERATION_METRICS }] : []),
  ];
  return (
    <div className="space-y-6">
      {groups.map((group) => (
        <Section key={group.title} title={group.title}>
          <div className={`grid grid-cols-2 gap-4 ${group.metrics.length > 4 ? "lg:grid-cols-5" : "lg:grid-cols-4"}`}>
            {group.metrics.map((metric) => {
              const value = summary.metrics[metric];
              const asPercent = PERCENT_METRICS.has(metric);
              return (
                <KpiTile
                  key={metric}
                  label={METRICS[metric].label}
                  value={asPercent ? percent(value, 1) : score(value)}
                  hint={METRICS[metric].description}
                  delta={deltaFor(gate, metric)}
                />
              );
            })}
          </div>
        </Section>
      ))}
    </div>
  );
}

function GateCard({ gate }: { gate: GateResult }) {
  const gated = gate.deltas.filter((d) => d.tolerance !== null);
  const changed = blockingDrift(gate);
  if (changed) {
    return (
      <div className="flex flex-wrap items-center gap-4 rounded-xl bg-warning/10 p-4 ring-1 ring-warning/30" role="status">
        <ShieldAlert className="size-6 text-warning" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold">Not comparable with the baseline</p>
          <p className="text-[13px] text-muted-foreground">
            {changed} changed since {gate.baseline_label}, so a
            metric diff would not mean anything. Promote a fresh baseline to gate again.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div
      className={`flex flex-wrap items-center gap-4 rounded-xl p-4 ring-1 ${gate.passed ? "bg-success/8 ring-success/25" : "bg-destructive/8 ring-destructive/25"}`}
      role="status"
    >
      {gate.passed ? (
        <ShieldCheck className="size-6 text-success" strokeWidth={1.75} aria-hidden />
      ) : (
        <ShieldAlert className="size-6 text-destructive" strokeWidth={1.75} aria-hidden />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold">
          {gate.passed ? "Quality gate passes against the baseline" : "This run would fail the quality gate"}
        </p>
        <p className="text-[13px] text-muted-foreground">Compared with {gate.baseline_label}</p>
      </div>
      <dl className="flex gap-6 text-[13px]">
        {gated.map((d) => (
          <div key={d.metric}>
            <dt className="text-muted-foreground">{METRICS[d.metric as MetricKey]?.label ?? d.metric}</dt>
            <dd className={`font-semibold tabular-nums ${d.regressed ? "text-destructive" : ""}`}>
              {signed(d.delta)} <span className="font-normal text-muted-foreground">(tolerance −{d.tolerance})</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function CostCard({ summary, run }: { summary: RunSummary; run: Run }) {
  const stages = Object.entries(summary.cost);
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Tokens and cost</CardTitle>
        <CardDescription>
          {usd(summary.total_cost_usd)} for the run · {usd(summary.cost_per_query_usd)} per question
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {stages.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Retrieval-only runs make no model calls.</p>
        ) : (
          <div className="divide-y divide-border rounded-lg ring-1 ring-border/70">
            {stages.map(([stage, cost]) => (
              <div key={stage} className="flex min-h-11 items-center justify-between gap-3 px-3 text-[13px]">
                <span className="font-medium">{STAGE_LABELS[stage] ?? stage}</span>
                <span className="text-muted-foreground tabular-nums">
                  {(cost.input_tokens + cost.output_tokens).toLocaleString()} tok · {usd(cost.cost_usd)}
                </span>
              </div>
            ))}
          </div>
        )}
        <dl className="space-y-1.5 text-[12px] text-muted-foreground">
          <div className="flex justify-between gap-2">
            <dt>Generator</dt>
            <dd className="font-mono">{run.llm_model}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>Judge</dt>
            <dd className="font-mono">{run.judge_model}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

const SORTS = [
  { value: "ndcg_asc", label: "Worst first" },
  { value: "ndcg_desc", label: "Best first" },
  { value: "question", label: "Golden order" },
] as const satisfies readonly { value: ResultSort; label: string }[];

function QuestionTable({ run }: { run: Run }) {
  const router = useRouter();
  const [sort, setSort] = useState<ResultSort>("ndcg_asc");
  const [page, setPage] = useState(1);
  const results = useRunResults(run.id, sort, page, run.status === "completed");
  const totalPages = results.data ? Math.max(1, Math.ceil(results.data.total / results.data.page_size)) : 1;
  const full = run.mode === "full";

  return (
    <Section
      title="Questions"
      description="Open a question to see what was retrieved next to the evidence it should have found."
      actions={
        <Segmented<ResultSort>
          label="Sort questions"
          value={sort}
          onValueChange={(next) => {
            setSort(next);
            setPage(1);
          }}
          options={SORTS}
        />
      }
    >
      {results.isPending ? (
        <TableSkeleton rows={8} />
      ) : results.isError ? (
        <ErrorState error={results.error} />
      ) : (
        <div className="overflow-x-auto rounded-xl bg-card shadow-xs ring-1 ring-border/70">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4 text-[12px] font-medium text-muted-foreground">Question</TableHead>
                <TableHead className="text-right text-[12px] font-medium text-muted-foreground">nDCG</TableHead>
                <TableHead className="text-right text-[12px] font-medium text-muted-foreground">Recall</TableHead>
                <TableHead className="text-right text-[12px] font-medium text-muted-foreground">MRR</TableHead>
                {full ? (
                  <TableHead className="text-right text-[12px] font-medium text-muted-foreground">Faithful</TableHead>
                ) : null}
                <TableHead className="text-[12px] font-medium text-muted-foreground">Outcome</TableHead>
                <TableHead className="text-right text-[12px] font-medium text-muted-foreground">Latency</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.data.items.map((row) => (
                <TableRow
                  key={row.question_id}
                  className="h-12 cursor-pointer hover:bg-accent/50"
                  onClick={() => router.push(`/runs/${run.id}/questions/${row.question_id}`)}
                >
                  <TableCell className="max-w-[420px] pl-4">
                    <Link
                      href={`/runs/${run.id}/questions/${row.question_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="line-clamp-1 font-medium whitespace-normal outline-none hover:underline focus-visible:underline"
                    >
                      {row.question}
                    </Link>
                    <p className="text-[12px] text-muted-foreground">
                      {row.external_id ?? "synthetic"} · {row.document_slug ?? "no source"}
                    </p>
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{score(row.metrics.ndcg_at_k, 2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{score(row.metrics.recall_at_k, 2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{score(row.metrics.mrr, 2)}</TableCell>
                  {full ? (
                    <TableCell className="text-right tabular-nums">{score(row.metrics.faithfulness, 2)}</TableCell>
                  ) : null}
                  <TableCell>
                    <Outcome row={row} full={full} />
                  </TableCell>
                  <TableCell className="text-right text-[13px] text-muted-foreground tabular-nums">{ms(row.total_ms)}</TableCell>
                  <TableCell className="pr-3 text-muted-foreground">
                    <ChevronRight className="size-4" strokeWidth={1.75} aria-hidden />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {totalPages > 1 ? (
            <div className="flex items-center justify-between border-t border-border/60 px-4 py-2.5 text-[13px]">
              <span className="text-muted-foreground tabular-nums">
                Page {page} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </Section>
  );
}

function Outcome({
  row,
  full,
}: {
  row: { answerable: boolean; metrics: { abstained: boolean; correct_abstention: boolean | null }; abstain_reason: string | null };
  full: boolean;
}) {
  if (!full) return <Pill>Retrieval</Pill>;
  if (!row.answerable) {
    return row.metrics.correct_abstention ? (
      <Pill tone="green">
        <CheckCircle2 className="size-3" aria-hidden /> Declined correctly
      </Pill>
    ) : (
      <Pill tone="red">Answered unanswerable</Pill>
    );
  }
  return row.metrics.abstained ? <Pill tone="orange">Abstained</Pill> : <Pill>Answered</Pill>;
}
