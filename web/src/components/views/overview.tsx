"use client";

import { BookOpen, ChevronRight, FlaskConical, Library } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { GateBadge } from "@/components/metrics/badges";
import { MAX_SERIES, MetricComparisonChart, QualityLatencyChart, seriesColors } from "@/components/metrics/charts";
import { KpiTile } from "@/components/metrics/kpi-tile";
import { EmptyState, ErrorState, TableSkeleton, TilesSkeleton } from "@/components/metrics/states";
import { Page, Section } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { LeaderboardRow } from "@/lib/api/schemas";
import { useCorpus, useHealth, useLeaderboard } from "@/lib/api/queries";
import { KIND_LABELS, METRICS, baselineStatus, ms, percent, score, signed, usd } from "@/lib/format";

function gateDelta(row: LeaderboardRow, metric: "ndcg_at_k" | "faithfulness") {
  const delta = row.gate?.deltas.find((d) => d.metric === metric)?.delta;
  return delta === null || delta === undefined ? null : { value: delta, text: `${signed(delta)} vs baseline` };
}

export function OverviewView() {
  const leaderboard = useLeaderboard();
  const rows = leaderboard.data ?? [];
  const best = rows[0];

  return (
    <Page
      title="Overview"
      subtitle="Every pipeline config scored against the same golden set. Higher is better unless noted."
      width="wide"
      actions={
        <Button asChild>
          <Link href="/runs?new=1">New run</Link>
        </Button>
      }
    >
      {leaderboard.isError ? <ErrorState error={leaderboard.error} onRetry={() => void leaderboard.refetch()} /> : null}

      {leaderboard.isPending ? (
        <div className="space-y-8">
          <TilesSkeleton />
          <TableSkeleton rows={5} />
        </div>
      ) : rows.length === 0 && !leaderboard.isError ? (
        <EmptyState
          icon={FlaskConical}
          title="No evaluation runs yet"
          description="Run `make seed` to index the corpus and score every pipeline, or start a run yourself."
          action={
            <Button asChild>
              <Link href="/runs?new=1">Start a run</Link>
            </Button>
          }
        />
      ) : best ? (
        <div className="space-y-10">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiTile
              label={`Best nDCG@k · ${best.config.name}`}
              value={score(best.metrics.ndcg_at_k)}
              hint={METRICS.ndcg_at_k.description}
              delta={gateDelta(best, "ndcg_at_k")}
              footnote={baselineStatus(best, "ndcg_at_k")}
            />
            <KpiTile
              label="Faithfulness"
              value={percent(best.metrics.faithfulness, 1)}
              hint={METRICS.faithfulness.description}
              delta={gateDelta(best, "faithfulness")}
              footnote="Judged claim by claim"
            />
            <KpiTile label="p95 latency" value={ms(best.p95_ms)} footnote={`p50 ${ms(best.p50_ms)}`} />
            <KpiTile
              label="Cost per query"
              value={usd(best.cost_per_query_usd)}
              hint="Generation, rewrite and judge tokens priced at list rates."
              footnote="Including the judge"
            />
          </div>

          <Section title="Leaderboard" description="Latest completed run for each config, ranked by nDCG@k.">
            <LeaderboardTable rows={rows} />
          </Section>

          <div className="grid gap-6 xl:grid-cols-5">
            <Card className="xl:col-span-3">
              <CardHeader>
                <CardTitle>Metrics side by side</CardTitle>
                <CardDescription>
                  Retrieval and generation quality{" "}
                  {rows.length > MAX_SERIES
                    ? `for the top ${MAX_SERIES} configs by nDCG@k (+${rows.length - MAX_SERIES} more in the leaderboard).`
                    : "for each config."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <MetricComparisonChart
                  rows={rows}
                  metrics={["ndcg_at_k", "recall_at_k", "mrr", "context_precision", "faithfulness", "answer_relevance"]}
                />
              </CardContent>
            </Card>
            <Card className="xl:col-span-2">
              <CardHeader>
                <CardTitle>Quality against latency</CardTitle>
                <CardDescription>
                  nDCG@k versus p95 end-to-end latency, log scale
                  {rows.length > MAX_SERIES ? `, top ${MAX_SERIES} configs` : ""}.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <QualityLatencyChart rows={rows} />
              </CardContent>
            </Card>
          </div>

          <CorpusSection />
        </div>
      ) : null}
    </Page>
  );
}

function LeaderboardTable({ rows }: { rows: LeaderboardRow[] }) {
  const router = useRouter();
  const colors = seriesColors(rows.slice(0, MAX_SERIES).map((r) => r.config.name));

  return (
    <div className="overflow-x-auto rounded-xl bg-card shadow-xs ring-1 ring-border/70">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-4 text-[12px] font-medium text-muted-foreground">Config</TableHead>
            {(["ndcg_at_k", "recall_at_k", "mrr", "faithfulness", "answer_relevance"] as const).map((m) => (
              <TableHead key={m} className="text-right text-[12px] font-medium text-muted-foreground">
                {METRICS[m].label}
              </TableHead>
            ))}
            <TableHead className="text-right text-[12px] font-medium text-muted-foreground">p95</TableHead>
            <TableHead className="text-right text-[12px] font-medium text-muted-foreground">Cost / q</TableHead>
            <TableHead className="text-[12px] font-medium text-muted-foreground">Gate</TableHead>
            <TableHead className="w-8" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow
              key={row.run_id}
              className="h-12 cursor-pointer hover:bg-accent/50"
              onClick={() => router.push(`/runs/${row.run_id}`)}
            >
              <TableCell className="pl-4">
                <div className="flex items-center gap-3">
                  <span className="w-4 text-[13px] text-muted-foreground tabular-nums">{index + 1}</span>
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: colors.get(row.config.name) ?? "var(--muted-foreground)", opacity: colors.has(row.config.name) ? 1 : 0.35 }}
                  />
                  <div className="min-w-0">
                    <Link
                      href={`/runs/${row.run_id}`}
                      className="font-medium outline-none hover:underline focus-visible:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {row.config.name}
                    </Link>
                    <p className="text-[12px] text-muted-foreground">
                      {KIND_LABELS[row.config.kind]} · v{row.config.version}
                    </p>
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{score(row.metrics.ndcg_at_k)}</TableCell>
              <TableCell className="text-right tabular-nums">{score(row.metrics.recall_at_k)}</TableCell>
              <TableCell className="text-right tabular-nums">{score(row.metrics.mrr)}</TableCell>
              <TableCell className="text-right tabular-nums">{score(row.metrics.faithfulness)}</TableCell>
              <TableCell className="text-right tabular-nums">{score(row.metrics.answer_relevance)}</TableCell>
              <TableCell className="text-right tabular-nums">{ms(row.p95_ms)}</TableCell>
              <TableCell className="text-right tabular-nums">{usd(row.cost_per_query_usd)}</TableCell>
              <TableCell>
                <GateBadge gate={row.gate} isBaseline={row.is_baseline} />
              </TableCell>
              <TableCell className="pr-3 text-muted-foreground">
                <ChevronRight className="size-4" strokeWidth={1.75} aria-hidden />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function CorpusSection() {
  const corpus = useCorpus();
  const health = useHealth();
  if (!corpus.data) return null;

  return (
    <Section
      title="Corpus"
      description={`${corpus.data.chunk_count.toLocaleString()} chunks from ${corpus.data.documents.length} public-domain books, embedded with ${corpus.data.embedding_model}.`}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <div className="divide-y divide-border rounded-xl bg-card shadow-xs ring-1 ring-border/70 md:col-span-2">
          {corpus.data.documents.map((doc) => (
            <div key={doc.slug} className="flex min-h-12 items-center justify-between gap-4 px-4 py-2">
              <div className="flex min-w-0 items-center gap-3">
                <BookOpen className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium">{doc.title}</p>
                  <p className="truncate text-[12px] text-muted-foreground">{doc.author}</p>
                </div>
              </div>
              <p className="shrink-0 text-[13px] text-muted-foreground tabular-nums">{doc.chunk_count} chunks</p>
            </div>
          ))}
        </div>
        <div className="space-y-3 rounded-xl bg-card p-5 shadow-xs ring-1 ring-border/70">
          <div className="flex items-center gap-2 text-[13px] font-medium">
            <Library className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
            Models
          </div>
          {health.data ? (
            <dl className="space-y-2 text-[13px]">
              {[
                ["Generator", health.data.llm_model],
                ["Judge", health.data.judge_model],
                ["Embeddings", health.data.embedding_model],
                ["Reranker", health.data.reranker_model],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="truncate font-mono text-[12px]">{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {health.data?.offline ? (
            <p className="rounded-lg bg-secondary px-3 py-2 text-[12px] text-muted-foreground">
              Offline mode: a deterministic extractive model stands in for Claude, so runs are free and reproducible.
              Costs show what the same tokens would cost on Claude.
            </p>
          ) : null}
        </div>
      </div>
    </Section>
  );
}
