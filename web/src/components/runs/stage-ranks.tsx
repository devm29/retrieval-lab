import { STAGE_LABELS } from "@/lib/format";

const ORDER = ["bm25", "dense", "rrf", "rerank"];

export function StageRanks({ ranks }: { ranks: Record<string, number> }) {
  const entries = ORDER.filter((stage) => ranks[stage] !== undefined);
  if (entries.length === 0) return null;
  return (
    <p className="text-[12px] text-muted-foreground tabular-nums">
      {entries.map((stage, index) => (
        <span key={stage}>
          {index > 0 ? <span aria-hidden> · </span> : null}
          {stage === "rrf" ? "RRF" : (STAGE_LABELS[stage] ?? stage)} #{ranks[stage]}
        </span>
      ))}
    </p>
  );
}
