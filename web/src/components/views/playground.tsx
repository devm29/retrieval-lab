"use client";

import { CircleHelp, CornerDownLeft, MessageSquareText, Sparkles } from "lucide-react";
import { useRef, useState } from "react";

import { Pill } from "@/components/metrics/badges";
import { ScoreBar } from "@/components/metrics/score-bar";
import { EmptyState, ErrorState } from "@/components/metrics/states";
import { CitedAnswer } from "@/components/playground/cited-answer";
import { Waterfall } from "@/components/playground/waterfall";
import { ChunkText } from "@/components/runs/chunk-text";
import { StageRanks } from "@/components/runs/stage-ranks";
import { Page, Section } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { QueryResponse } from "@/lib/api/schemas";
import { useAsk, useConfigs } from "@/lib/api/queries";
import { configLabel, rewriteLabel, score, specView, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const SAMPLES = [
  "Why do a piece of lead and a piece of wood fall the same way?",
  "Who presides when the President is tried for impeachment?",
  "What makes a candle flame bright?",
  "What does Sun Tzu consider the highest form of military excellence?",
  "Who won the 1998 FIFA World Cup?",
];

const ABSTAIN_TITLE: Record<string, string> = {
  low_evidence: "Not enough evidence to answer",
  model_declined: "The passages don't contain the answer",
  no_results: "Nothing matched this question",
};

export function PlaygroundView() {
  const configs = useConfigs();
  const latest = (configs.data ?? []).filter((c) => c.is_latest);
  const [config, setConfig] = useState("hybrid-rerank");
  const [question, setQuestion] = useState("");
  const [focused, setFocused] = useState<number | null>(null);
  const ask = useAsk();
  const sourcesRef = useRef<HTMLOListElement>(null);

  const submit = (text = question) => {
    const trimmed = text.trim();
    if (trimmed.length < 3 || ask.isPending) return;
    setFocused(null);
    ask.mutate({ question: trimmed, config });
  };

  const cite = (marker: number) => {
    setFocused(marker);
    sourcesRef.current?.querySelector(`[data-marker="${marker}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <Page title="Playground" subtitle="Ask the library a question and watch each stage of the pipeline answer it.">
      <Card className="mb-8">
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="question" className="text-[13px] font-medium">
                Question
              </Label>
              <Textarea
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="What does Einstein say about the speed of light?"
                rows={3}
                maxLength={1000}
                className="resize-none rounded-lg text-[15px]"
              />
            </div>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="space-y-2">
                <Label htmlFor="config" className="text-[13px] font-medium">
                  Pipeline
                </Label>
                <Select value={config} onValueChange={setConfig}>
                  <SelectTrigger id="config" className="h-9 w-60 rounded-lg">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {latest.map((c) => (
                      <SelectItem key={c.id} value={c.name}>
                        {configLabel(c)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
                {ask.isPending ? "Thinking…" : "Ask"}
                <kbd className="ml-1 hidden items-center gap-0.5 rounded bg-primary-foreground/20 px-1 text-[11px] sm:inline-flex">
                  ⌘<CornerDownLeft className="size-3" aria-hidden />
                </kbd>
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {SAMPLES.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  onClick={() => {
                    setQuestion(sample);
                    submit(sample);
                  }}
                  className="rounded-full bg-secondary px-3 py-1 text-[13px] text-secondary-foreground transition-colors duration-150 hover:bg-accent focus-visible:ring-4 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {sample}
                </button>
              ))}
            </div>
          </form>
        </CardContent>
      </Card>

      {ask.isError ? <ErrorState title="The question couldn't be answered" error={ask.error} /> : null}
      {ask.isPending ? <AnswerSkeleton /> : null}
      {ask.data && !ask.isPending ? (
        <PlaygroundResult data={ask.data} focused={focused} onCite={cite} sourcesRef={sourcesRef} />
      ) : null}
      {!ask.data && !ask.isPending && !ask.isError ? (
        <EmptyState
          icon={MessageSquareText}
          title="Ask anything about the six books"
          description="Relativity, the Constitution, The Art of War, Faraday's candle lectures, Flatland and The Elements of Style."
        />
      ) : null}
    </Page>
  );
}

function AnswerSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Answering">
      <Skeleton className="h-36 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

export function PlaygroundResult({
  data,
  focused,
  onCite,
  sourcesRef,
}: {
  data: QueryResponse;
  focused: number | null;
  onCite: (marker: number) => void;
  sourcesRef: React.RefObject<HTMLOListElement | null>;
}) {
  const { answer, retrieval, timings_ms } = data.result;
  const citedIds = new Map(answer.citations.map((c) => [c.chunk_id, c.marker]));
  const valid = new Set(answer.citations.map((c) => c.marker));
  const { maxContextChunks, rewriteAppliesTo } = specView(data.config.spec);

  return (
    <div className="space-y-8" aria-live="polite">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {answer.abstained ? (
              <CircleHelp className="size-4 text-warning" strokeWidth={1.75} aria-hidden />
            ) : (
              <Sparkles className="size-4 text-primary" strokeWidth={1.75} aria-hidden />
            )}
            {answer.abstained ? ABSTAIN_TITLE[answer.abstain_reason ?? "no_results"] : "Answer"}
          </CardTitle>
          <CardDescription>
            {configLabel(data.config)} · {answer.model ?? "no model call"} · top evidence{" "}
            {score(answer.top_evidence_score, 2)} · {usd(data.total_cost_usd)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {answer.abstained ? (
            <p className="text-[15px] text-muted-foreground">
              {answer.text} Rather than guess, the pipeline declines when retrieval can&apos;t back an answer.
            </p>
          ) : (
            <CitedAnswer text={answer.text} validMarkers={valid} onCite={onCite} />
          )}
          {retrieval.rewritten_query && rewriteAppliesTo ? (
            <p className="text-[13px] text-muted-foreground">
              {rewriteLabel(rewriteAppliesTo)}: <span className="font-mono text-[12px]">{retrieval.rewritten_query}</span>
            </p>
          ) : null}
          <div className="space-y-2">
            <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Where the time went</p>
            <Waterfall timings={timings_ms} />
          </div>
        </CardContent>
      </Card>

      <Section
        title="Sources"
        description={`Final ranking. The top ${maxContextChunks} went to the model; cited passages are numbered as they appear in the answer.`}
      >
        <ol ref={sourcesRef} className="space-y-3">
          {retrieval.chunks.map((chunk, index) => {
            const marker = citedIds.get(chunk.chunk_id) ?? null;
            const inContext = index < maxContextChunks;
            return (
              <li
                key={chunk.chunk_id}
                data-marker={index + 1}
                className={cn(
                  "rounded-xl bg-card p-4 shadow-xs ring-1 ring-border/70 transition-shadow duration-200",
                  focused === index + 1 && "ring-2 ring-primary",
                )}
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-md text-[12px] font-semibold tabular-nums",
                        marker ? "bg-primary text-primary-foreground" : "bg-secondary",
                      )}
                    >
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium">{chunk.heading || chunk.document_title}</p>
                      <p className="truncate text-[12px] text-muted-foreground">{chunk.document_title}</p>
                    </div>
                  </div>
                  {marker ? <Pill tone="blue">Cited</Pill> : inContext ? <Pill>In context</Pill> : null}
                </div>
                <ChunkText content={chunk.content} clamp={!marker} />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <StageRanks ranks={chunk.stage_ranks} />
                  <div className="flex w-40 items-center gap-2">
                    <ScoreBar value={chunk.evidence_score} label={`Evidence score for source ${index + 1}`} />
                    <span className="text-[12px] text-muted-foreground tabular-nums">{score(chunk.evidence_score, 2)}</span>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </Section>
    </div>
  );
}
