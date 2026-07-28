"use client";

import { CheckCircle2, Scale, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Pill } from "@/components/metrics/badges";
import { KpiTile } from "@/components/metrics/kpi-tile";
import { EmptyState, ErrorState, TilesSkeleton } from "@/components/metrics/states";
import { Page, Section } from "@/components/shell/page";
import { InlineMarkdown } from "@/components/text/inline-markdown";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import type { Calibration } from "@/lib/api/schemas";
import { useCalibration, useRecalibrate } from "@/lib/api/queries";
import { ago, percent, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const LABELS = ["faithful", "unfaithful"] as const;

export function JudgeView() {
  const calibration = useCalibration();
  const recalibrate = useRecalibrate();
  const notCalibrated = calibration.error instanceof ApiError && calibration.error.status === 404;

  const run = () =>
    recalibrate.mutate(undefined, {
      onSuccess: (data) => toast.success(`Kappa ${data.report.kappa.toFixed(2)} (${data.report.interpretation})`),
      onError: (error) => toast.error(error.message),
    });

  return (
    <Page
      title="Judge calibration"
      subtitle="How far to trust the LLM judge: its faithfulness verdicts compared with human labels."
      actions={
        <Button onClick={run} disabled={recalibrate.isPending}>
          {recalibrate.isPending ? "Calibrating…" : "Recalibrate"}
        </Button>
      }
    >
      {calibration.isPending ? <TilesSkeleton /> : null}
      {notCalibrated ? (
        <EmptyState
          icon={Scale}
          title="The judge hasn't been calibrated"
          description="Score it against the human-labelled set to see Cohen's kappa before trusting faithfulness numbers."
          action={<Button onClick={run}>Calibrate now</Button>}
        />
      ) : calibration.isError ? (
        <ErrorState error={calibration.error} onRetry={() => void calibration.refetch()} />
      ) : null}
      {calibration.data ? <Report calibration={calibration.data} /> : null}
    </Page>
  );
}

function Report({ calibration }: { calibration: Calibration }) {
  const { report } = calibration;
  const disagreements = report.items.filter((item) => !item.agree);
  const agreements = report.items.filter((item) => item.agree);

  return (
    <div className="space-y-10">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile
          label="Cohen's kappa"
          value={report.kappa.toFixed(2)}
          hint="Agreement corrected for chance. Above 0.6 is substantial; 0.4 to 0.6 is moderate."
          footnote={`${report.interpretation[0]?.toUpperCase() ?? ""}${report.interpretation.slice(1)} agreement`}
        />
        <KpiTile label="Raw agreement" value={percent(report.agreement)} footnote={`${report.sample_size} labelled answers`} />
        <KpiTile label="Disagreements" value={String(disagreements.length)} footnote="Listed below for review" />
        <KpiTile
          label="Judge"
          value={report.judge_model.replace(/^claude-/, "")}
          footnote={`${ago(calibration.created_at)} · ${usd(report.usage.cost_usd)}`}
          className="[&_p:nth-child(2)]:truncate [&_p:nth-child(2)]:text-[20px]"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Section title="Confusion matrix" description="Rows are human labels, columns the judge's.">
          <table className="w-full overflow-hidden rounded-xl bg-card text-[13px] shadow-xs ring-1 ring-border/70">
            <caption className="sr-only">Human versus judge labels</caption>
            <thead>
              <tr className="text-muted-foreground">
                <th scope="col" className="p-3 text-left font-medium">
                  Human ↓ Judge →
                </th>
                {LABELS.map((label) => (
                  <th key={label} scope="col" className="p-3 text-right font-medium capitalize">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {LABELS.map((human) => (
                <tr key={human} className="border-t border-border/60">
                  <th scope="row" className="p-3 text-left font-medium capitalize">
                    {human}
                  </th>
                  {LABELS.map((judge) => {
                    const count = report.confusion[human]?.[judge] ?? 0;
                    return (
                      <td
                        key={judge}
                        className={cn(
                          "p-3 text-right text-[17px] font-semibold tabular-nums",
                          human === judge ? "text-foreground" : count ? "text-destructive" : "text-muted-foreground",
                        )}
                      >
                        {count}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[12px] text-muted-foreground">
            Off-diagonal cells are where the judge and the human disagree. A judge that only matches on easy items will
            show high raw agreement but a low kappa.
          </p>
        </Section>

        <Section title="Where they disagree" description="Each item shows the answer, both labels and the judge's claim checks.">
          <ul className="space-y-3">
            {[...disagreements, ...agreements].map((item) => (
              <li key={item.id} className="rounded-xl bg-card p-4 shadow-xs ring-1 ring-border/70">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[13px] font-medium">{item.question}</p>
                  <div className="flex gap-1.5">
                    <Pill tone={item.human_label === "faithful" ? "green" : "red"}>Human: {item.human_label}</Pill>
                    <Pill tone={item.agree ? "neutral" : "orange"}>Judge: {item.judge_label}</Pill>
                  </div>
                </div>
                <p className="text-[14px] text-foreground/90">
                  <InlineMarkdown text={item.answer} />
                </p>
                {item.note ? <p className="mt-1 text-[12px] text-muted-foreground">Note: {item.note}</p> : null}
                {!item.agree ? (
                  <ul className="mt-3 space-y-1">
                    {item.claims.map((claim, index) => (
                      <li key={index} className="flex gap-2 text-[12px] text-muted-foreground">
                        {claim.supported ? (
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="Supported" />
                        ) : (
                          <XCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-label="Unsupported" />
                        )}
                        <span>
                          <InlineMarkdown text={claim.claim} />
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  );
}
