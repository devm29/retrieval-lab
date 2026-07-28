import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, request } from "./client";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("parses a valid response and builds the query string", async () => {
    mockFetch(200, { ok: true });
    const result = await request("/health", z.object({ ok: z.boolean() }), { query: { page: 2, config: undefined } });
    expect(result).toEqual({ ok: true });
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("/api/health?page=2");
  });

  it("surfaces the API error envelope", async () => {
    mockFetch(422, { error: { code: "validation_failed", message: "Request validation failed", details: [{ loc: ["body", "question"], msg: "too short" }] } });
    await expect(request("/query", z.object({}))).rejects.toMatchObject({
      status: 422,
      code: "validation_failed",
      message: "Request validation failed (question: too short)",
    });
  });

  it("rejects responses that don't match the schema", async () => {
    mockFetch(200, { ok: "yes" });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(request("/health", z.object({ ok: z.boolean() }))).rejects.toBeInstanceOf(ApiError);
  });

  it("reports network failures with a helpful message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    await expect(request("/health", z.object({}))).rejects.toMatchObject({ code: "network_error" });
  });
});
