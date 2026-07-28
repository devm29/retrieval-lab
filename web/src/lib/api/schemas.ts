import { z } from "zod";

const nullableNumber = z.number().nullable();

const rewriteTargetSchema = z.enum(["bm25", "dense", "both"]);
export type RewriteTarget = z.infer<typeof rewriteTargetSchema>;

export const tokenUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: z.number(),
});

export const aggregateMetricsSchema = z.object({
  recall_at_k: nullableNumber,
  mrr: nullableNumber,
  ndcg_at_k: nullableNumber,
  context_precision: nullableNumber,
  faithfulness: nullableNumber,
  answer_relevance: nullableNumber,
  citation_accuracy: nullableNumber,
  abstention_accuracy: nullableNumber,
  false_abstention_rate: nullableNumber,
});
export type AggregateMetrics = z.infer<typeof aggregateMetricsSchema>;
export type MetricKey = keyof AggregateMetrics;

const latencyStatsSchema = z.object({ p50: z.number(), p95: z.number(), mean: z.number() });

export const runSummarySchema = z.object({
  k: z.number(),
  mode: z.enum(["full", "retrieval"]),
  question_count: z.number(),
  answerable_count: z.number(),
  unanswerable_count: z.number(),
  metrics: aggregateMetricsSchema,
  latency_ms: z.record(z.string(), latencyStatsSchema),
  cost: z.record(z.string(), tokenUsageSchema),
  total_cost_usd: z.number(),
  cost_per_query_usd: z.number(),
});
export type RunSummary = z.infer<typeof runSummarySchema>;

export const configSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  version: z.number(),
  kind: z.enum(["bm25", "dense", "hybrid", "hybrid_rerank"]),
  spec_hash: z.string(),
  description: z.string(),
  spec: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  is_latest: z.boolean(),
});
export type PipelineConfig = z.infer<typeof configSchema>;

/** The parts of a stored spec the UI labels depend on; the rest is free-form JSON. */
export const specViewSchema = z.object({
  generation: z.object({ max_context_chunks: z.number() }).partial().optional(),
  query_rewrite: z.object({ apply_to: rewriteTargetSchema }).nullable().optional(),
});

export const configCreatedSchema = z.object({ config: configSchema, created: z.boolean() });

export const runStatusSchema = z.enum(["queued", "running", "completed", "failed"]);
export type RunStatus = z.infer<typeof runStatusSchema>;

export const runSchema = z.object({
  id: z.uuid(),
  config: configSchema,
  status: runStatusSchema,
  mode: z.string(),
  trigger: z.string(),
  label: z.string().nullable(),
  k: z.number(),
  question_count: z.number(),
  completed_count: z.number(),
  llm_model: z.string(),
  judge_model: z.string(),
  summary: runSummarySchema.nullable(),
  error: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  is_baseline: z.boolean(),
});
export type Run = z.infer<typeof runSchema>;

export function pageSchema<T extends z.ZodType>(item: T) {
  return z.object({
    items: z.array(item),
    total: z.number(),
    page: z.number(),
    page_size: z.number(),
  });
}

const metricDeltaSchema = z.object({
  metric: z.string(),
  baseline: nullableNumber,
  candidate: nullableNumber,
  delta: nullableNumber,
  tolerance: nullableNumber,
  regressed: z.boolean(),
});
export type MetricDelta = z.infer<typeof metricDeltaSchema>;

const driftItemSchema = z.object({
  field: z.string(),
  baseline: z.string().nullable(),
  candidate: z.string().nullable(),
  blocking: z.boolean(),
});
export type DriftItem = z.infer<typeof driftItemSchema>;

export const gateResultSchema = z.object({
  passed: z.boolean(),
  config_name: z.string(),
  baseline_label: z.string(),
  candidate_label: z.string(),
  tolerance: z.object({ ndcg_at_k: z.number(), faithfulness: z.number() }),
  deltas: z.array(metricDeltaSchema),
  drift: z.array(driftItemSchema).default([]),
});
export type GateResult = z.infer<typeof gateResultSchema>;

export const leaderboardRowSchema = z.object({
  config: configSchema,
  run_id: z.uuid(),
  finished_at: z.string().nullable(),
  metrics: aggregateMetricsSchema,
  p50_ms: nullableNumber,
  p95_ms: nullableNumber,
  cost_per_query_usd: z.number(),
  gate: gateResultSchema.nullable(),
  is_baseline: z.boolean(),
});
export type LeaderboardRow = z.infer<typeof leaderboardRowSchema>;

export const historyPointSchema = z.object({
  run_id: z.uuid(),
  version: z.number(),
  finished_at: z.string().nullable(),
  label: z.string().nullable(),
  metrics: aggregateMetricsSchema,
});
export type HistoryPoint = z.infer<typeof historyPointSchema>;

const questionMetricsSchema = z.object({
  recall_at_k: nullableNumber,
  mrr: nullableNumber,
  ndcg_at_k: nullableNumber,
  context_precision: nullableNumber,
  faithfulness: nullableNumber,
  answer_relevance: nullableNumber,
  citation_accuracy: nullableNumber,
  abstained: z.boolean(),
  correct_abstention: z.boolean().nullable(),
});
export type QuestionMetrics = z.infer<typeof questionMetricsSchema>;

export const resultRowSchema = z.object({
  question_id: z.uuid(),
  external_id: z.string().nullable(),
  question: z.string(),
  answerable: z.boolean(),
  document_slug: z.string().nullable(),
  metrics: questionMetricsSchema,
  abstain_reason: z.string().nullable(),
  total_ms: nullableNumber,
});
export type ResultRow = z.infer<typeof resultRowSchema>;

const citationSchema = z.object({
  marker: z.number(),
  chunk_id: z.string(),
  document_title: z.string(),
  heading: z.string(),
  snippet: z.string(),
});
export type Citation = z.infer<typeof citationSchema>;

const claimSchema = z.object({ claim: z.string(), supported: z.boolean() });
const span = z.tuple([z.number(), z.number()]).nullable();

export const resultDetailSchema = z.object({
  run_id: z.uuid(),
  config_name: z.string(),
  k: z.number(),
  max_context_chunks: z.number(),
  rewrite_applies_to: rewriteTargetSchema.nullable(),
  result: z.object({
    question_id: z.string(),
    question: z.string(),
    answerable: z.boolean(),
    document_slug: z.string().nullable(),
    evidence: z.string().nullable(),
    evidence_found: z.boolean(),
    rewritten_query: z.string().nullable(),
    metrics: questionMetricsSchema,
    answer: z.string().nullable(),
    abstain_reason: z.string().nullable(),
    citations: z.array(citationSchema),
    claims: z.array(claimSchema),
    relevance_reason: z.string().nullable(),
    timings_ms: z.record(z.string(), z.number()),
    usage: z.record(z.string(), tokenUsageSchema),
  }),
  retrieved: z.array(
    z.object({
      chunk_id: z.string(),
      rank: z.number(),
      document_slug: z.string(),
      document_title: z.string(),
      heading: z.string(),
      content: z.string().nullable(),
      score: z.number(),
      evidence_score: z.number(),
      coverage: z.number(),
      relevant: z.boolean(),
      stage_ranks: z.record(z.string(), z.number()),
      highlight: span,
    }),
  ),
  expected: z.array(
    z.object({
      chunk_id: z.string(),
      coverage: z.number(),
      retrieved_rank: z.number().nullable(),
      heading: z.string().nullable(),
      content: z.string().nullable(),
      highlight: span,
    }),
  ),
});
export type ResultDetail = z.infer<typeof resultDetailSchema>;

const retrievedChunkSchema = z.object({
  chunk_id: z.string(),
  rank: z.number(),
  document_slug: z.string(),
  document_title: z.string(),
  heading: z.string(),
  content: z.string(),
  score: z.number(),
  evidence_score: z.number(),
  stage_scores: z.record(z.string(), z.number()),
  stage_ranks: z.record(z.string(), z.number()),
});
export type RetrievedChunk = z.infer<typeof retrievedChunkSchema>;

export const queryResponseSchema = z.object({
  config: configSchema,
  total_cost_usd: z.number(),
  result: z.object({
    question: z.string(),
    answer: z.object({
      text: z.string(),
      citations: z.array(citationSchema),
      invalid_markers: z.array(z.number()),
      abstained: z.boolean(),
      abstain_reason: z.enum(["no_results", "low_evidence", "model_declined"]).nullable(),
      top_evidence_score: nullableNumber,
      model: z.string().nullable(),
    }),
    retrieval: z.object({
      query: z.string(),
      rewritten_query: z.string().nullable(),
      chunks: z.array(retrievedChunkSchema),
      timings_ms: z.record(z.string(), z.number()),
    }),
    timings_ms: z.record(z.string(), z.number()),
    usage: z.record(z.string(), tokenUsageSchema),
  }),
});
export type QueryResponse = z.infer<typeof queryResponseSchema>;

export const goldenStatusSchema = z.enum(["proposed", "accepted", "rejected"]);
export type GoldenStatus = z.infer<typeof goldenStatusSchema>;

export const goldenQuestionSchema = z.object({
  id: z.uuid(),
  external_id: z.string().nullable(),
  question: z.string(),
  document_slug: z.string().nullable(),
  evidence: z.string().nullable(),
  reference_answer: z.string().nullable(),
  answerable: z.boolean(),
  status: goldenStatusSchema,
  origin: z.enum(["seed", "synthetic", "manual"]),
  source_chunk_id: z.string().nullable(),
  created_at: z.string(),
  reviewed_at: z.string().nullable(),
});
export type GoldenQuestion = z.infer<typeof goldenQuestionSchema>;

export const goldenPageSchema = pageSchema(goldenQuestionSchema).extend({
  counts: z.record(z.string(), z.number()),
});
export type GoldenPage = z.infer<typeof goldenPageSchema>;

export const synthesizeResponseSchema = z.object({
  created: z.number(),
  skipped: z.number(),
  cost_usd: z.number(),
  questions: z.array(goldenQuestionSchema),
});

export const healthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  database: z.boolean(),
  offline: z.boolean(),
  llm_model: z.string(),
  judge_model: z.string(),
  embedding_model: z.string(),
  reranker_model: z.string(),
  chunk_count: z.number(),
});
export type Health = z.infer<typeof healthSchema>;

export const corpusSchema = z.object({
  documents: z.array(
    z.object({
      slug: z.string(),
      title: z.string(),
      author: z.string().nullable(),
      source_url: z.string().nullable(),
      characters: z.number(),
      chunk_count: z.number(),
    }),
  ),
  chunk_count: z.number(),
  embedding_model: z.string(),
});
export type Corpus = z.infer<typeof corpusSchema>;

export const compareSchema = z.object({
  baseline: runSchema,
  candidate: runSchema,
  gate: gateResultSchema,
  questions: z.array(
    z.object({
      question_id: z.uuid(),
      question: z.string(),
      baseline_ndcg: nullableNumber,
      candidate_ndcg: nullableNumber,
      delta: nullableNumber,
    }),
  ),
});
export type CompareResult = z.infer<typeof compareSchema>;

const label = z.enum(["faithful", "unfaithful"]);

export const calibrationSchema = z.object({
  id: z.uuid(),
  created_at: z.string(),
  report: z.object({
    judge_model: z.string(),
    sample_size: z.number(),
    kappa: z.number(),
    agreement: z.number(),
    interpretation: z.string(),
    confusion: z.record(z.string(), z.record(z.string(), z.number())),
    items: z.array(
      z.object({
        id: z.string(),
        question: z.string(),
        answer: z.string(),
        human_label: label,
        judge_label: label,
        judge_score: nullableNumber,
        claims: z.array(claimSchema),
        agree: z.boolean(),
        note: z.string().nullable(),
      }),
    ),
    usage: tokenUsageSchema,
  }),
});
export type Calibration = z.infer<typeof calibrationSchema>;

export const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.array(z.object({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() })).optional(),
  }),
});
