import { type GateResult, type LeaderboardRow, type MetricKey, type RewriteTarget, specViewSchema } from "./api/schemas";

export interface MetricInfo {
  label: string;
  short: string;
  description: string;
  lowerIsBetter?: boolean;
}

export const METRICS: Record<MetricKey, MetricInfo> = {
  ndcg_at_k: {
    label: "nDCG@k",
    short: "nDCG",
    description: "Ranking quality, crediting evidence that appears higher in the list.",
  },
  recall_at_k: {
    label: "Recall@k",
    short: "Recall",
    description: "Share of the evidence span covered by the top k chunks.",
  },
  mrr: { label: "MRR", short: "MRR", description: "Reciprocal rank of the first relevant chunk." },
  context_precision: {
    label: "Context precision",
    short: "Ctx precision",
    description:
      "Average precision of the top k, with the judge marking which passages help reach the reference answer. Full runs only.",
  },
  faithfulness: {
    label: "Faithfulness",
    short: "Faithful",
    description: "Share of answer claims the judge found supported by the context.",
  },
  answer_relevance: {
    label: "Answer relevance",
    short: "Relevance",
    description: "Judge score for how directly the answer addresses the question.",
  },
  citation_accuracy: {
    label: "Citation accuracy",
    short: "Citations",
    description: "Share of citations that point at chunks containing the gold evidence.",
  },
  abstention_accuracy: {
    label: "Abstention accuracy",
    short: "Abstention",
    description: "Unanswerable questions the system correctly declined.",
  },
  false_abstention_rate: {
    label: "False abstention",
    short: "False abst.",
    description: "Answerable questions the system declined to answer.",
    lowerIsBetter: true,
  },
};

export const RETRIEVAL_METRICS: MetricKey[] = ["ndcg_at_k", "recall_at_k", "mrr", "context_precision"];
export const GENERATION_METRICS: MetricKey[] = [
  "faithfulness",
  "answer_relevance",
  "citation_accuracy",
  "abstention_accuracy",
  "false_abstention_rate",
];

export const STAGE_LABELS: Record<string, string> = {
  rewrite: "Rewrite",
  bm25: "BM25",
  embed: "Embed",
  dense: "Dense",
  fusion: "Fusion",
  rerank: "Rerank",
  retrieval: "Retrieval",
  generate: "Generate",
  judge: "Judge",
  total: "Total",
};

export const KIND_LABELS: Record<string, string> = {
  bm25: "BM25",
  dense: "Dense",
  hybrid: "Hybrid RRF",
  hybrid_rerank: "Hybrid + rerank",
};

export function score(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

export function percent(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(value < 10 ? 1 : 0)} ms`;
}

export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "$0";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

export function signed(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—";
  const fixed = value.toFixed(digits);
  return value > 0 ? `+${fixed}` : fixed;
}

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function ago(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return relative.format(seconds, "second");
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86_400), "day");
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function configLabel(config: { name: string; version: number }): string {
  return `${config.name}@${config.version}`;
}

/** What the KPI tile says when there is no delta to show. */
export function baselineStatus(row: Pick<LeaderboardRow, "gate" | "is_baseline">, metric: MetricKey): string {
  if (row.is_baseline) return "This run is the baseline";
  const gate = row.gate;
  if (!gate) return "No baseline yet";
  if (gate.drift.some((d) => d.blocking)) return "Not comparable with its baseline";
  if (!gate.passed) return "Gate failed vs baseline";
  const delta = gate.deltas.find((d) => d.metric === metric)?.delta;
  return delta === 0 ? "Matches its baseline" : "Within tolerance of its baseline";
}

export interface SpecView {
  maxContextChunks: number;
  rewriteAppliesTo: RewriteTarget | null;
}

export function specView(spec: Record<string, unknown>): SpecView {
  const parsed = specViewSchema.safeParse(spec);
  const data = parsed.success ? parsed.data : {};
  return {
    maxContextChunks: data.generation?.max_context_chunks ?? 5,
    rewriteAppliesTo: data.query_rewrite?.apply_to ?? null,
  };
}

export function rewriteLabel(target: RewriteTarget): string {
  switch (target) {
    case "bm25":
      return "BM25 searched for";
    case "dense":
      return "Dense search embedded";
    case "both":
      return "BM25 and dense searched for";
  }
}

const DRIFT_LABELS: Record<string, string> = {
  golden_hash: "The golden set",
  embedding_model: "The embedding model",
  reranker_model: "The reranker",
  llm_model: "The generator",
  judge_model: "The judge",
  k: "The cut-off k",
  environment: "The recorded environment",
};

/** The blocking differences between two runs as a sentence subject, or null when they are comparable. */
export function blockingDrift(gate: Pick<GateResult, "drift">): string | null {
  const blocking = gate.drift.filter((d) => d.blocking);
  if (blocking.length === 0) return null;
  const labels = blocking.map((d) => DRIFT_LABELS[d.field] ?? d.field);
  return labels.map((label, i) => (i === 0 ? label : label.charAt(0).toLowerCase() + label.slice(1))).join(", ");
}
