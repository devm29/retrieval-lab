import { STAGE_LABELS, ms } from "@/lib/format";

interface Bar {
  stage: string;
  start: number;
  duration: number;
}

/** Reconstructs the stage schedule: rewrite, then BM25 alongside embed→dense, then fusion, rerank, generate. */
export function scheduleStages(timings: Record<string, number>): Bar[] {
  const t = (stage: string) => timings[stage] ?? 0;
  const bars: Bar[] = [];
  let cursor = 0;
  if (timings.rewrite !== undefined) {
    bars.push({ stage: "rewrite", start: 0, duration: t("rewrite") });
    cursor = t("rewrite");
  }
  const parallelStart = cursor;
  let parallelEnd = cursor;
  if (timings.bm25 !== undefined) {
    bars.push({ stage: "bm25", start: parallelStart, duration: t("bm25") });
    parallelEnd = Math.max(parallelEnd, parallelStart + t("bm25"));
  }
  if (timings.embed !== undefined) {
    bars.push({ stage: "embed", start: parallelStart, duration: t("embed") });
    const denseStart = parallelStart + t("embed");
    if (timings.dense !== undefined) {
      bars.push({ stage: "dense", start: denseStart, duration: t("dense") });
    }
    parallelEnd = Math.max(parallelEnd, denseStart + t("dense"));
  }
  cursor = parallelEnd;
  for (const stage of ["fusion", "rerank"]) {
    if (timings[stage] !== undefined) {
      bars.push({ stage, start: cursor, duration: t(stage) });
      cursor += t(stage);
    }
  }
  if (timings.generate !== undefined) {
    const generateStart = Math.max(cursor, (timings.total ?? cursor) - t("generate"));
    bars.push({ stage: "generate", start: generateStart, duration: t("generate") });
  }
  return bars;
}

export function Waterfall({ timings }: { timings: Record<string, number> }) {
  const bars = scheduleStages(timings);
  const total = Math.max(timings.total ?? 0, ...bars.map((b) => b.start + b.duration), 1);

  return (
    <div className="space-y-2" role="table" aria-label="Stage timings">
      {bars.map((bar) => (
        <div key={bar.stage} role="row" className="grid grid-cols-[72px_1fr_64px] items-center gap-3 text-[12px]">
          <span role="rowheader" className="text-muted-foreground">
            {STAGE_LABELS[bar.stage] ?? bar.stage}
          </span>
          <div role="cell" className="relative h-2 rounded-full bg-secondary">
            <div
              className="absolute h-2 rounded-full bg-primary"
              style={{
                left: `${(bar.start / total) * 100}%`,
                width: `${Math.max((bar.duration / total) * 100, 0.8)}%`,
              }}
            />
          </div>
          <span role="cell" className="text-right tabular-nums">
            {ms(bar.duration)}
          </span>
        </div>
      ))}
    </div>
  );
}
