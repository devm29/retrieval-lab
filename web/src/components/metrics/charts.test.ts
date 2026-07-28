import { describe, expect, it } from "vitest";

import { logTicks } from "./charts";

describe("logTicks", () => {
  it("brackets the range with 1-2-5 steps", () => {
    expect(logTicks(26, 758)).toEqual([20, 50, 100, 200, 500, 1000]);
  });

  it("covers a range that sits on a single step", () => {
    expect(logTicks(100, 100)).toEqual([100]);
  });
});
