import type { z } from "zod";

import { errorEnvelopeSchema } from "./schemas";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `/api${path}${search ? `?${search}` : ""}`;
}

export async function request<T extends z.ZodType>(
  path: string,
  schema: T,
  { method = "GET", query, body, signal }: RequestOptions = {},
): Promise<z.infer<T>> {
  const init: RequestInit = { method, headers: { accept: "application/json" } };
  if (signal) init.signal = signal;
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { ...init.headers, "content-type": "application/json" };
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), init);
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the Retrieval Lab API. Is the backend running on port 8102?");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = errorEnvelopeSchema.safeParse(payload);
    if (envelope.success) {
      const { code, message, details } = envelope.data.error;
      const first = details?.[0];
      const detail = first ? ` (${first.loc.filter((part) => part !== "body").join(".")}: ${first.msg})` : "";
      throw new ApiError(response.status, code, `${message}${detail}`);
    }
    throw new ApiError(response.status, "http_error", `Request failed with status ${response.status}`);
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    console.error(`Unexpected response shape from ${path}`, parsed.error.issues);
    throw new ApiError(response.status, "invalid_response", "The API returned data in an unexpected shape.");
  }
  return parsed.data;
}
