import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Waterfall, scheduleStages } from "./waterfall";

describe("scheduleStages", () => {
  it("runs BM25 alongside embed and dense, then fusion and rerank", () => {
    const bars = scheduleStages({ bm25: 20, embed: 30, dense: 10, fusion: 1, rerank: 100, generate: 5, total: 140 });
    const byStage = Object.fromEntries(bars.map((b) => [b.stage, b]));
    expect(byStage.bm25?.start).toBe(0);
    expect(byStage.embed?.start).toBe(0);
    expect(byStage.dense?.start).toBe(30);
    expect(byStage.fusion?.start).toBe(40);
    expect(byStage.rerank?.start).toBe(41);
    expect(byStage.generate?.start).toBe(141);
  });

  it("offsets everything by the rewrite stage", () => {
    const bars = scheduleStages({ rewrite: 50, bm25: 10 });
    expect(bars.find((b) => b.stage === "bm25")?.start).toBe(50);
  });
});

describe("Waterfall", () => {
  it("labels each stage with its duration", () => {
    render(<Waterfall timings={{ bm25: 12, embed: 30, dense: 8, total: 40 }} />);
    expect(screen.getByText("BM25")).toBeInTheDocument();
    expect(screen.getByText("30 ms")).toBeInTheDocument();
  });
});
