"use client";

import { CheckCircle2, CircleSlash, Quote, XCircle } from "lucide-react";

import { Pill } from "@/components/metrics/badges";
import { CitedAnswer } from "@/components/playground/cited-answer";
import { ScoreBar } from "@/components/metrics/score-bar";
import { ErrorState, TableSkeleton } from "@/components/metrics/states";
import { ChunkText } from "@/components/runs/chunk-text";
import { StageRanks } from "@/components/runs/stage-ranks";
import { InlineMarkdown } from "@/components/text/inline-markdown";
import { Page, Section } from "@/components/shell/page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Citation, ResultDetail } from "@/lib/api/schemas";
import { useResultDetail } from "@/lib/api/queries";
import { STAGE_LABELS, ms, percent, rewriteLabel, score, shortId } from "@/lib/format";
import { cn } from "@/lib/utils";

const ABSTAIN_COPY: Record<string, string> = {
  low_evidence: "Abstained: the best evidence scored below the config's threshold.",
  model_declined: "Abstained: the model judged the passages insufficient.",
  no_results: "Abstained: nothing matched the question.",
};

export function QuestionDetailView({ runId, questionId }: { runId: string; questionId: string }) {
  const detail = useResultDetail(runId, questionId);
  const back = { href: `/runs/${runId}`, label: "Run" };

  if (detail.isError) {
    return (
      <Page title="Question" back={back}>
        <ErrorState title="We couldn't load this question" error={detail.error} onRetry={() => void detail.refetch()} />
      </Page>
    );
  }
  if (!detail.data) {
    return (
      <Page title="Question" back={back}>
        <TableSkeleton rows={8} />
      </Page>
    );
  }

  const { result, retrieved, expected, k, rewrite_applies_to: rewriteTarget } = detail.data;
  const m = result.metrics;

  return (
    <Page
      title={result.question}
      back={back}
      width="wide"
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <span>
            {detail.data.config_name} · run {shortId(runId)} · top {k}
          </span>
          {result.answerable ? <Pill>Answerable</Pill> : <Pill tone="orange">Unanswerable by design</Pill>}
          {m.abstained ? <Pill tone={result.answerable ? "orange" : "green"}>Abstained</Pill> : null}
        </span>
      }
    >
      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {(
          [
            ["nDCG@k", score(m.ndcg_at_k, 2)],
            ["Recall@k", score(m.recall_at_k, 2)],
            ["MRR", score(m.mrr, 2)],
            ["Context precision", score(m.context_precision, 2)],
            ["Faithfulness", percent(m.faithfulness)],
            ["Answer relevance", score(m.answer_relevance, 2)],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded-xl bg-card px-4 py-3 shadow-xs ring-1 ring-border/70">
            <p className="text-[12px] text-muted-foreground">{label}</p>
            <p className="text-[20px] font-semibold tracking-tight tabular-nums">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          {result.evidence ? <EvidenceCard detail={detail.data} /> : null}
          <AnswerCard detail={detail.data} />
          <ExpectedList expected={expected} />
        </div>
        <Section
          title={`Retrieved top ${retrieved.length}`}
          description={
            result.rewritten_query && rewriteTarget
              ? `${rewriteLabel(rewriteTarget)} “${result.rewritten_query}”.`
              : "In final ranking order."
          }
        >
          <ol className="space-y-3">
            {retrieved.map((chunk) => (
              <li
                key={chunk.chunk_id}
                data-chunk-id={chunk.chunk_id}
                className={cn(
                  "scroll-mt-20 rounded-xl bg-card p-4 shadow-xs ring-1",
                  chunk.relevant ? "ring-success/40" : "ring-border/70",
                )}
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-secondary text-[12px] font-semibold tabular-nums">
                      {chunk.rank}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium">{chunk.heading || chunk.document_title}</p>
                      <p className="truncate text-[12px] text-muted-foreground">
                        {chunk.document_title} · <span className="font-mono">{chunk.chunk_id}</span>
                      </p>
                    </div>
                  </div>
                  {chunk.relevant ? (
                    <Pill tone="green">
                      <CheckCircle2 className="size-3" aria-hidden /> Evidence {percent(chunk.coverage)}
                    </Pill>
                  ) : chunk.coverage > 0 ? (
                    <Pill tone="orange">Partial {percent(chunk.coverage)}</Pill>
                  ) : (
                    <Pill>Not evidence</Pill>
                  )}
                </div>
                {chunk.content ? <ChunkText content={chunk.content} highlight={chunk.highlight} clamp={!chunk.relevant} /> : null}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <StageRanks ranks={chunk.stage_ranks} />
                  <div className="flex w-40 items-center gap-2">
                    <ScoreBar value={chunk.evidence_score} label={`Evidence score for rank ${chunk.rank}`} />
                    <span className="text-[12px] text-muted-foreground tabular-nums">{score(chunk.evidence_score, 2)}</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </Section>
      </div>
    </Page>
  );
}

function EvidenceCard({ detail }: { detail: ResultDetail }) {
  const { result } = detail;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Quote className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          Gold evidence
        </CardTitle>
        <CardDescription>
          From {result.document_slug}
          {result.evidence_found ? "" : " · not found in the current corpus, so retrieval metrics are skipped"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <blockquote className="border-l-2 border-primary/60 pl-3 text-[15px] leading-[23px]">
          {result.evidence ? <InlineMarkdown text={result.evidence} /> : null}
        </blockquote>
      </CardContent>
    </Card>
  );
}

function scrollToCitation(citations: readonly Citation[], marker: number) {
  const chunkId = citations.find((c) => c.marker === marker)?.chunk_id;
  if (!chunkId) return;
  document.querySelector(`[data-chunk-id="${CSS.escape(chunkId)}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function AnswerCard({ detail }: { detail: ResultDetail }) {
  const { result } = detail;
  if (result.answer === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Answer</CardTitle>
          <CardDescription>Retrieval-only run: no answer was generated.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const timings = Object.entries(result.timings_ms).filter(([stage]) => stage !== "total" && stage !== "retrieval");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Answer</CardTitle>
        <CardDescription>
          {result.abstain_reason ? ABSTAIN_COPY[result.abstain_reason] : `${result.citations.length} ${result.citations.length === 1 ? "citation" : "citations"}`} · total{" "}
          {ms(result.timings_ms.total)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {result.abstain_reason ? (
          <p className="text-[15px] leading-[23px] text-muted-foreground">
            <InlineMarkdown text={result.answer} />
          </p>
        ) : (
          <CitedAnswer
            text={result.answer}
            validMarkers={new Set(result.citations.map((c) => c.marker))}
            onCite={(marker) => scrollToCitation(result.citations, marker)}
            className="text-[15px] leading-[23px]"
          />
        )}
        {result.claims.length ? (
          <div className="space-y-2">
            <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Judge verdicts</p>
            <ul className="space-y-1.5">
              {result.claims.map((claim, index) => (
                <li key={index} className="flex gap-2 text-[13px]">
                  {claim.supported ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" strokeWidth={1.75} aria-label="Supported" />
                  ) : (
                    <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" strokeWidth={1.75} aria-label="Unsupported" />
                  )}
                  <span>
                    <InlineMarkdown text={claim.claim} />
                  </span>
                </li>
              ))}
            </ul>
            {result.relevance_reason ? (
              <p className="text-[12px] text-muted-foreground">Relevance: {result.relevance_reason}</p>
            ) : null}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground tabular-nums">
          {timings.map(([stage, value]) => (
            <span key={stage}>
              {STAGE_LABELS[stage] ?? stage} {ms(value)}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ExpectedList({ expected }: { expected: ResultDetail["expected"] }) {
  if (expected.length === 0) return null;
  return (
    <Section title="Where the evidence lives" description="Every chunk that overlaps the gold span, and where it ranked.">
      <ul className="space-y-3">
        {expected.map((chunk) => (
          <li key={chunk.chunk_id} className="rounded-xl bg-card p-4 shadow-xs ring-1 ring-border/70">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="truncate text-[13px] font-medium">
                {chunk.heading} <span className="font-mono text-[12px] font-normal text-muted-foreground">{chunk.chunk_id}</span>
              </p>
              {chunk.retrieved_rank ? (
                <Pill tone="green">Rank {chunk.retrieved_rank}</Pill>
              ) : (
                <Pill tone="red">
                  <CircleSlash className="size-3" aria-hidden /> Missed
                </Pill>
              )}
            </div>
            {chunk.content ? <ChunkText content={chunk.content} highlight={chunk.highlight} clamp /> : null}
            <p className="mt-2 text-[12px] text-muted-foreground tabular-nums">Covers {percent(chunk.coverage)} of the evidence</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
