import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import type { QueryResponse } from "@/lib/api/schemas";

import { PlaygroundResult } from "./playground";

function response(spec: Record<string, unknown>, chunkCount: number): QueryResponse {
  const chunks = Array.from({ length: chunkCount }, (_, i) => ({
    chunk_id: `flatland:${String(i).padStart(4, "0")}`,
    rank: i + 1,
    document_slug: "flatland",
    document_title: "Flatland",
    heading: `Section ${i + 1}`,
    content: `Passage number ${i + 1}.`,
    score: 1 - i / 10,
    evidence_score: 0.5,
    stage_scores: {},
    stage_ranks: { bm25: i + 1 },
  }));
  return {
    config: {
      id: crypto.randomUUID(),
      name: "probe",
      version: 1,
      kind: "hybrid_rerank",
      spec_hash: "0".repeat(64),
      description: "",
      spec,
      created_at: new Date().toISOString(),
      is_latest: true,
    },
    total_cost_usd: 0,
    result: {
      question: "What shape are women?",
      answer: {
        text: "Straight lines [1].",
        citations: [
          { marker: 1, chunk_id: "flatland:0000", document_title: "Flatland", heading: "Section 1", snippet: "" },
        ],
        invalid_markers: [],
        abstained: false,
        abstain_reason: null,
        top_evidence_score: 0.5,
        model: "fake-extractive-v1",
      },
      retrieval: { query: "What shape are women?", rewritten_query: "women shape figure", chunks, timings_ms: {} },
      timings_ms: { total: 12 },
      usage: {},
    },
  };
}

function renderResult(data: QueryResponse) {
  render(<PlaygroundResult data={data} focused={null} onCite={() => undefined} sourcesRef={createRef()} />);
}

describe("PlaygroundResult", () => {
  it("marks as many sources in context as the config sends to the model", () => {
    renderResult(response({ generation: { max_context_chunks: 3 }, query_rewrite: { apply_to: "bm25" } }, 8));
    expect(screen.getAllByText("Cited")).toHaveLength(1);
    expect(screen.getAllByText("In context")).toHaveLength(2);
  });

  it("names the stages the rewrite was applied to", () => {
    renderResult(response({ generation: { max_context_chunks: 5 }, query_rewrite: { apply_to: "both" } }, 2));
    expect(screen.getByText(/BM25 and dense searched for/)).toBeInTheDocument();
  });
});
