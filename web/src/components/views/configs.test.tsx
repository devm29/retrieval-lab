import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PipelineConfig } from "@/lib/api/schemas";
import { renderWithClient } from "@/test/render";

import { NewVersionDialog } from "./configs";

function config(name: string, spec: Record<string, unknown>): PipelineConfig {
  return {
    id: crypto.randomUUID(),
    name,
    version: 1,
    kind: "bm25",
    spec_hash: "0".repeat(64),
    description: "",
    spec,
    created_at: new Date().toISOString(),
    is_latest: true,
  };
}

const rerank = config("hybrid-rerank", { kind: "hybrid_rerank", top_k: 10, rerank_candidates: 30 });
const bm25 = config("bm25", { kind: "bm25", top_k: 10 });
const pretty = (c: PipelineConfig) => JSON.stringify(c.spec, null, 2);

describe("NewVersionDialog", () => {
  it("edits the spec of the config that is selected when it opens", () => {
    const noop = () => undefined;
    const { rerender } = renderWithClient(<NewVersionDialog base={rerank} open={false} onOpenChange={noop} />);
    rerender(<NewVersionDialog base={bm25} open onOpenChange={noop} />);
    expect(screen.getByRole("dialog", { name: "New version of bm25" })).toBeInTheDocument();
    expect(screen.getByLabelText("Spec")).toHaveValue(pretty(bm25));
  });

  it("discards abandoned edits when reopened", () => {
    const noop = () => undefined;
    const { rerender } = renderWithClient(<NewVersionDialog base={bm25} open onOpenChange={noop} />);
    fireEvent.change(screen.getByLabelText("Spec"), { target: { value: "{ half-typed" } });
    rerender(<NewVersionDialog base={bm25} open={false} onOpenChange={noop} />);
    rerender(<NewVersionDialog base={bm25} open onOpenChange={noop} />);
    expect(screen.getByLabelText("Spec")).toHaveValue(pretty(bm25));
  });
});
