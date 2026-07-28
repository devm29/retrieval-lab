"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";

import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { HistoryPoint, LeaderboardRow, MetricKey, RunSummary } from "@/lib/api/schemas";
import { METRICS, STAGE_LABELS, ms, score } from "@/lib/format";

/** The palette has five distinguishable hues; charts never show more series than that. */
export const MAX_SERIES = 5;

/**
 * Colour follows the config, not its rank: slots are assigned by sorted name so re-ranking never
 * repaints. Callers pass at most MAX_SERIES names; anything beyond gets no colour.
 */
export function seriesColors(names: readonly string[]): Map<string, string> {
  const sorted = [...new Set(names)].sort().slice(0, MAX_SERIES);
  return new Map(sorted.map((name, index) => [name, `var(--chart-${index + 1})`]));
}

const AXIS = { tickLine: false, axisLine: false, tickMargin: 8, fontSize: 11 } as const;

/** 1-2-5 ticks that bracket [min, max], for a log axis that otherwise shows a single label. */
export function logTicks(min: number, max: number): number[] {
  const steps: number[] = [];
  for (let exponent = -1; exponent <= 6; exponent += 1) {
    for (const mantissa of [1, 2, 5]) steps.push(mantissa * 10 ** exponent);
  }
  const low = steps.findLast((step) => step <= min) ?? 0;
  const high = steps.find((step) => step >= max) ?? Infinity;
  return steps.filter((step) => step >= low && step <= high);
}

/** Even ticks from `low` to 1, `step` apart, rounded to dodge float drift. */
function scoreTicks(low: number, step: number): number[] {
  const count = Math.round((1 - low) / step);
  return Array.from({ length: count + 1 }, (_, index) => Math.round((low + index * step) * 100) / 100);
}

export function MetricComparisonChart({ rows, metrics }: { rows: LeaderboardRow[]; metrics: MetricKey[] }) {
  const shown = rows.slice(0, MAX_SERIES);
  const colors = seriesColors(shown.map((r) => r.config.name));
  const config: ChartConfig = Object.fromEntries(
    shown.map((r) => [r.config.name, { label: r.config.name, color: colors.get(r.config.name) ?? "var(--chart-1)" }]),
  );
  const data = metrics.map((metric) => ({
    metric: METRICS[metric].short,
    ...Object.fromEntries(shown.map((r) => [r.config.name, r.metrics[metric] ?? 0])),
  }));

  return (
    <ChartContainer config={config} className="aspect-auto h-[300px] w-full">
      <BarChart data={data} barGap={2} barCategoryGap="22%" accessibilityLayer>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="metric" {...AXIS} />
        <YAxis domain={[0, 1]} tickCount={6} width={40} tickFormatter={(v: number) => v.toFixed(1)} {...AXIS} />
        <ChartTooltip cursor={{ fillOpacity: 0.4 }} content={<ChartTooltipContent valueFormatter={(v) => score(Number(v))} />} />
        <ChartLegend content={<ChartLegendContent />} />
        {shown.map((r) => (
          <Bar key={r.config.name} dataKey={r.config.name} fill={`var(--color-${r.config.name})`} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

export function QualityLatencyChart({ rows }: { rows: LeaderboardRow[] }) {
  const shown = rows.slice(0, MAX_SERIES);
  const colors = seriesColors(shown.map((r) => r.config.name));
  const config: ChartConfig = Object.fromEntries(
    shown.map((r) => [r.config.name, { label: r.config.name, color: colors.get(r.config.name) ?? "var(--chart-1)" }]),
  );
  const plotted = shown.flatMap((r) =>
    r.p95_ms === null ? [] : [{ name: r.config.name, latency: r.p95_ms, ndcg: r.metrics.ndcg_at_k ?? 0 }],
  );
  const latencies = plotted.map((p) => p.latency);
  const xTicks = latencies.length ? logTicks(Math.min(...latencies), Math.max(...latencies)) : [];
  const [xFirst] = xTicks;
  const xLast = xTicks.at(-1);
  const xRange =
    xFirst !== undefined && xLast !== undefined
      ? { domain: [xFirst, xLast] as const, ticks: xTicks }
      : { domain: ["auto", "auto"] as const };
  const floor = Math.max(0, Math.min(1, ...plotted.map((p) => p.ndcg)) - 0.05);
  const yStep = floor < 0.5 ? 0.1 : 0.05;
  const yLow = Math.floor(Math.round(floor * 1000) / 1000 / yStep) * yStep;
  const yTicks = scoreTicks(yLow, yStep);

  return (
    <ChartContainer config={config} className="aspect-auto h-[300px] w-full">
      <ScatterChart margin={{ top: 16, right: 24, bottom: 8, left: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="latency"
          name="p95 latency"
          scale="log"
          {...xRange}
          interval={0}
          tickFormatter={(v: number) => ms(v)}
          {...AXIS}
        />
        <YAxis
          type="number"
          dataKey="ndcg"
          name="nDCG@k"
          domain={[yLow, 1]}
          ticks={yTicks}
          interval={0}
          tickFormatter={(v: number) => v.toFixed(2)}
          width={40}
          {...AXIS}
        />
        <ZAxis range={[90, 90]} />
        <ChartTooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) => String(payload[0]?.payload?.name ?? "")}
              valueFormatter={(value, item) => (item.dataKey === "latency" ? ms(Number(value)) : score(Number(value)))}
            />
          }
        />
        {plotted.map((point) => (
          <Scatter
            key={point.name}
            name={point.name}
            data={[point]}
            fill={`var(--color-${point.name})`}
            stroke="var(--card)"
            strokeWidth={2}
          />
        ))}
        <ChartLegend content={<ChartLegendContent className="flex-wrap gap-x-4 gap-y-1" />} />
      </ScatterChart>
    </ChartContainer>
  );
}

const STAGE_ORDER = ["rewrite", "bm25", "embed", "dense", "fusion", "rerank", "retrieval", "generate", "total"];

export function LatencyChart({ summary }: { summary: RunSummary }) {
  const data = STAGE_ORDER.filter((stage) => summary.latency_ms[stage]).map((stage) => ({
    stage: STAGE_LABELS[stage] ?? stage,
    p50: summary.latency_ms[stage]?.p50 ?? 0,
    p95: summary.latency_ms[stage]?.p95 ?? 0,
  }));
  const config: ChartConfig = {
    p50: { label: "p50", color: "var(--chart-1)" },
    p95: { label: "p95", color: "var(--chart-3)" },
  };

  return (
    <ChartContainer config={config} className="aspect-auto h-[280px] w-full">
      <BarChart data={data} layout="vertical" barGap={2} margin={{ left: 8, right: 16 }} accessibilityLayer>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" />
        <XAxis type="number" tickFormatter={(v: number) => ms(v)} {...AXIS} />
        <YAxis type="category" dataKey="stage" width={72} {...AXIS} />
        <ChartTooltip content={<ChartTooltipContent valueFormatter={(v) => ms(Number(v))} />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="p50" fill="var(--color-p50)" radius={[0, 4, 4, 0]} />
        <Bar dataKey="p95" fill="var(--color-p95)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartContainer>
  );
}

export function HistoryChart({ points }: { points: HistoryPoint[] }) {
  const data = points.map((p, index) => ({
    run: `v${p.version} · ${index + 1}`,
    ndcg: p.metrics.ndcg_at_k,
    faithfulness: p.metrics.faithfulness,
  }));
  const config: ChartConfig = {
    ndcg: { label: "nDCG@k", color: "var(--chart-1)" },
    faithfulness: { label: "Faithfulness", color: "var(--chart-2)" },
  };

  return (
    <ChartContainer config={config} className="aspect-auto h-[240px] w-full">
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="run" {...AXIS} />
        <YAxis domain={[0, 1]} tickCount={6} width={40} tickFormatter={(v: number) => v.toFixed(1)} {...AXIS} />
        <ChartTooltip content={<ChartTooltipContent valueFormatter={(v) => score(Number(v))} />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Line type="monotone" dataKey="ndcg" stroke="var(--color-ndcg)" strokeWidth={2} dot={{ r: 4 }} />
        <Line type="monotone" dataKey="faithfulness" stroke="var(--color-faithfulness)" strokeWidth={2} dot={{ r: 4 }} />
      </LineChart>
    </ChartContainer>
  );
}
