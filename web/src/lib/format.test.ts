import { describe, expect, it } from "vitest";

import { ago, baselineStatus, blockingDrift, ms, percent, rewriteLabel, score, signed, specView, usd } from "./format";

describe("format", () => {
  it("renders missing values as an em dash", () => {
    expect(score(null)).toBe("—");
    expect(percent(undefined)).toBe("—");
    expect(ms(null)).toBe("—");
  });

  it("formats scores, percentages and signed deltas", () => {
    expect(score(0.86219)).toBe("0.862");
    expect(percent(0.9375, 1)).toBe("93.8%");
    expect(signed(0.0123)).toBe("+0.012");
    expect(signed(-0.5, 1)).toBe("-0.5");
  });

  it("switches latency units at one second", () => {
    expect(ms(4.21)).toBe("4.2 ms");
    expect(ms(817)).toBe("817 ms");
    expect(ms(1530)).toBe("1.53 s");
  });

  it("keeps small costs readable", () => {
    expect(usd(0)).toBe("$0");
    expect(usd(0.00573)).toBe("$0.0057");
    expect(usd(1.5)).toBe("$1.50");
  });

  it("describes relative time", () => {
    const now = Date.parse("2026-10-04T12:00:00Z");
    expect(ago("2026-10-04T11:58:00Z", now)).toBe("2 minutes ago");
    expect(ago("2026-10-03T12:00:00Z", now)).toBe("yesterday");
  });
});

describe("baselineStatus", () => {
  const gate = {
    passed: true,
    config_name: "c",
    baseline_label: "b",
    candidate_label: "c",
    tolerance: { ndcg_at_k: 0.02, faithfulness: 0.03 },
    deltas: [{ metric: "ndcg_at_k", baseline: 0.8, candidate: 0.8, delta: 0, tolerance: 0.02, regressed: false }],
    drift: [],
  };

  it("only claims a match when the gate passed with no change", () => {
    expect(baselineStatus({ gate, is_baseline: false }, "ndcg_at_k")).toBe("Matches its baseline");
    expect(baselineStatus({ gate: null, is_baseline: false }, "ndcg_at_k")).toBe("No baseline yet");
    expect(baselineStatus({ gate: { ...gate, passed: false }, is_baseline: false }, "ndcg_at_k")).toBe(
      "Gate failed vs baseline",
    );
    const drifted = { ...gate, drift: [{ field: "golden_hash", baseline: "a", candidate: "b", blocking: true }] };
    expect(baselineStatus({ gate: drifted, is_baseline: false }, "ndcg_at_k")).toBe("Not comparable with its baseline");
  });
});

describe("specView", () => {
  it("reads the context size and rewrite target, with safe defaults", () => {
    expect(specView({ generation: { max_context_chunks: 8 }, query_rewrite: { apply_to: "dense" } })).toEqual({
      maxContextChunks: 8,
      rewriteAppliesTo: "dense",
    });
    expect(specView({ kind: "bm25" })).toEqual({ maxContextChunks: 5, rewriteAppliesTo: null });
    expect(rewriteLabel("dense")).toBe("Dense search embedded");
  });
});

describe("blockingDrift", () => {
  it("names only the blocking differences", () => {
    const drift = [
      { field: "k", baseline: "10", candidate: "20", blocking: true },
      { field: "spec_hash", baseline: "a", candidate: "b", blocking: false },
      { field: "embedding_model", baseline: "x", candidate: "y", blocking: true },
    ];
    expect(blockingDrift({ drift })).toBe("The cut-off k, the embedding model");
    expect(blockingDrift({ drift: drift.filter((d) => !d.blocking) })).toBeNull();
  });
});
