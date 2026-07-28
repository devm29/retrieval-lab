"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { z } from "zod";

import { request } from "./client";
import {
  calibrationSchema,
  compareSchema,
  configCreatedSchema,
  configSchema,
  corpusSchema,
  gateResultSchema,
  goldenPageSchema,
  goldenQuestionSchema,
  type GoldenStatus,
  healthSchema,
  historyPointSchema,
  leaderboardRowSchema,
  pageSchema,
  queryResponseSchema,
  resultDetailSchema,
  resultRowSchema,
  runSchema,
  synthesizeResponseSchema,
} from "./schemas";

export type ResultSort = "ndcg_asc" | "ndcg_desc" | "question";

export const keys = {
  health: ["health"] as const,
  corpus: ["corpus"] as const,
  configs: ["configs"] as const,
  leaderboard: ["leaderboard"] as const,
  history: (name: string) => ["history", name] as const,
  runs: (filters: { config?: string; page: number }) => ["runs", filters] as const,
  run: (id: string) => ["run", id] as const,
  results: (id: string, sort: ResultSort, page: number) => ["results", id, sort, page] as const,
  result: (runId: string, questionId: string) => ["result", runId, questionId] as const,
  gate: (runId: string) => ["gate", runId] as const,
  compare: (baseline: string, candidate: string) => ["compare", baseline, candidate] as const,
  golden: (status: GoldenStatus, page: number) => ["golden", status, page] as const,
  calibration: ["calibration"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: ({ signal }) => request("/health", healthSchema, { signal }),
    refetchInterval: 30_000,
  });
}

export function useCorpus() {
  return useQuery({ queryKey: keys.corpus, queryFn: ({ signal }) => request("/corpus", corpusSchema, { signal }) });
}

export function useConfigs() {
  return useQuery({
    queryKey: keys.configs,
    queryFn: ({ signal }) => request("/configs", z.array(configSchema), { signal }),
  });
}

export function useLeaderboard() {
  return useQuery({
    queryKey: keys.leaderboard,
    queryFn: ({ signal }) => request("/leaderboard", z.array(leaderboardRowSchema), { signal }),
  });
}

export function useConfigHistory(name: string | undefined) {
  return useQuery({
    queryKey: keys.history(name ?? ""),
    queryFn: ({ signal }) => request(`/configs/${name ?? ""}/history`, z.array(historyPointSchema), { signal }),
    enabled: Boolean(name),
  });
}

const runPageSchema = pageSchema(runSchema);

export function useRuns(filters: { config?: string; page: number }, pageSize = 20) {
  return useQuery({
    queryKey: keys.runs(filters),
    queryFn: ({ signal }) =>
      request("/runs", runPageSchema, {
        signal,
        query: { config: filters.config, page: filters.page, page_size: pageSize },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 1500 : false,
  });
}

export function useRun(id: string) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.run(id),
    queryFn: ({ signal }) => request(`/runs/${id}`, runSchema, { signal }),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1000 : false;
    },
  });

  // Lists that summarise runs go stale the moment a polled run finishes.
  const status = query.data?.status;
  const previous = useRef(status);
  useEffect(() => {
    const was = previous.current;
    previous.current = status;
    if ((was === "queued" || was === "running") && (status === "completed" || status === "failed")) {
      void Promise.all([
        client.invalidateQueries({ queryKey: ["runs"] }),
        client.invalidateQueries({ queryKey: keys.leaderboard }),
        client.invalidateQueries({ queryKey: ["history"] }),
      ]);
    }
  }, [client, status]);

  return query;
}

const resultPageSchema = pageSchema(resultRowSchema);

export function useRunResults(id: string, sort: ResultSort, page: number, enabled = true) {
  return useQuery({
    queryKey: keys.results(id, sort, page),
    queryFn: ({ signal }) =>
      request(`/runs/${id}/results`, resultPageSchema, { signal, query: { sort, page, page_size: 25 } }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useResultDetail(runId: string, questionId: string) {
  return useQuery({
    queryKey: keys.result(runId, questionId),
    queryFn: ({ signal }) => request(`/runs/${runId}/results/${questionId}`, resultDetailSchema, { signal }),
  });
}

export function useRunGate(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.gate(runId),
    queryFn: ({ signal }) => request(`/runs/${runId}/gate`, gateResultSchema, { signal }),
    enabled,
    retry: false,
  });
}

export function useCompare(baseline: string | null, candidate: string | null) {
  return useQuery({
    queryKey: keys.compare(baseline ?? "", candidate ?? ""),
    queryFn: ({ signal }) =>
      request("/compare", compareSchema, { signal, query: { baseline, candidate } }),
    enabled: Boolean(baseline && candidate),
  });
}

export function useStartRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { config: string; mode: "full" | "retrieval"; label?: string }) =>
      request("/runs", runSchema, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["runs"] }),
  });
}

export function usePromoteBaseline() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => request("/baselines", runSchema, { method: "POST", body: { run_id: runId } }),
    onSuccess: async (run) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: keys.run(run.id) }),
        client.invalidateQueries({ queryKey: ["runs"] }),
        client.invalidateQueries({ queryKey: ["gate"] }),
        client.invalidateQueries({ queryKey: keys.leaderboard }),
      ]);
    },
  });
}

export function useAsk() {
  return useMutation({
    mutationFn: (body: { question: string; config: string }) =>
      request("/query", queryResponseSchema, { method: "POST", body }),
  });
}

export function useGolden(status: GoldenStatus, page: number) {
  return useQuery({
    queryKey: keys.golden(status, page),
    queryFn: ({ signal }) =>
      request("/golden", goldenPageSchema, { signal, query: { status, page, page_size: 50 } }),
    placeholderData: keepPreviousData,
  });
}

export interface GoldenPatch {
  question?: string;
  evidence?: string | null;
  reference_answer?: string | null;
  status?: GoldenStatus;
}

export function useUpdateGolden() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: GoldenPatch }) =>
      request(`/golden/${id}`, goldenQuestionSchema, { method: "PATCH", body: patch }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["golden"] }),
  });
}

export function useSynthesize() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (count: number) =>
      request("/golden/synthesize", synthesizeResponseSchema, { method: "POST", body: { count } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["golden"] }),
  });
}

export function useCreateConfig() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description: string; spec: Record<string, unknown> }) =>
      request("/configs", configCreatedSchema, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.configs }),
  });
}

export function useCalibration() {
  return useQuery({
    queryKey: keys.calibration,
    queryFn: ({ signal }) => request("/judge/calibration", calibrationSchema, { signal }),
    retry: false,
  });
}

export function useRecalibrate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request("/judge/calibration", calibrationSchema, { method: "POST" }),
    onSuccess: (data) => client.setQueryData(keys.calibration, data),
  });
}
