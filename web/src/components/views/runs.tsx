"use client";

import { ListChecks } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Pill, StatusBadge } from "@/components/metrics/badges";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/metrics/states";
import { NewRunDialog } from "@/components/runs/new-run-dialog";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useConfigs, useRuns } from "@/lib/api/queries";
import { ago, configLabel, ms, score } from "@/lib/format";

const ALL = "all";

export function RunsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [filter, setFilter] = useState<string>(ALL);
  const [page, setPage] = useState(1);
  const dialogOpen = params.get("new") === "1";
  const configs = useConfigs();
  const names = [...new Set((configs.data ?? []).map((c) => c.name))].sort();
  const runs = useRuns({ ...(filter === ALL ? {} : { config: filter }), page });
  const totalPages = runs.data ? Math.max(1, Math.ceil(runs.data.total / runs.data.page_size)) : 1;

  const setDialog = (open: boolean) => router.replace(open ? `${pathname}?new=1` : pathname, { scroll: false });

  return (
    <Page
      title="Runs"
      subtitle="Every evaluation, newest first. Open a run to see per-question results."
      actions={<Button onClick={() => setDialog(true)}>New run</Button>}
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select
          value={filter}
          onValueChange={(value) => {
            setFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-8 w-56 rounded-lg text-[13px]" aria-label="Filter by config">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All configs</SelectItem>
            {names.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {runs.data ? (
          <p className="text-[13px] text-muted-foreground tabular-nums">{runs.data.total} runs</p>
        ) : null}
      </div>

      {runs.isError ? <ErrorState error={runs.error} onRetry={() => void runs.refetch()} /> : null}
      {runs.isPending ? (
        <TableSkeleton />
      ) : runs.data && runs.data.items.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No runs for this filter"
          description="Start a run to score a config against the golden set."
          action={<Button onClick={() => setDialog(true)}>New run</Button>}
        />
      ) : runs.data ? (
        <div className="overflow-x-auto rounded-xl bg-card shadow-xs ring-1 ring-border/70">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {["Config", "Status", "nDCG@k", "Faithfulness", "p95", "Trigger", "Started"].map((h, i) => (
                  <TableHead
                    key={h}
                    className={`text-[12px] font-medium text-muted-foreground ${i === 0 ? "pl-4" : ""} ${i >= 2 && i <= 4 ? "text-right" : ""}`}
                  >
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.items.map((run) => (
                <TableRow
                  key={run.id}
                  className="h-12 cursor-pointer hover:bg-accent/50"
                  onClick={() => router.push(`/runs/${run.id}`)}
                >
                  <TableCell className="pl-4">
                    <Link
                      href={`/runs/${run.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium outline-none hover:underline focus-visible:underline"
                    >
                      {configLabel(run.config)}
                    </Link>
                    <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      {run.label ?? (run.mode === "retrieval" ? "Retrieval only" : "Full run")}
                      {run.is_baseline ? <Pill tone="blue">Baseline</Pill> : null}
                    </p>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {score(run.summary?.metrics.ndcg_at_k)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{score(run.summary?.metrics.faithfulness)}</TableCell>
                  <TableCell className="text-right tabular-nums">{ms(run.summary?.latency_ms.total?.p95)}</TableCell>
                  <TableCell className="text-[13px] text-muted-foreground capitalize">{run.trigger}</TableCell>
                  <TableCell className="text-[13px] text-muted-foreground">{ago(run.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {totalPages > 1 ? (
            <div className="flex items-center justify-between border-t border-border/60 px-4 py-2.5 text-[13px]">
              <span className="text-muted-foreground tabular-nums">
                Page {page} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <NewRunDialog open={dialogOpen} onOpenChange={setDialog} />
    </Page>
  );
}
