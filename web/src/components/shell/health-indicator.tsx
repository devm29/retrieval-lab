"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHealth } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

export function HealthIndicator() {
  const { data, isError } = useHealth();
  const healthy = data?.status === "ok" && !isError;
  const label = isError ? "API unreachable" : !data ? "Connecting…" : data.offline ? "Offline mode" : "Live models";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className="flex min-h-8 items-center gap-2 rounded-md px-2 text-[12px] text-muted-foreground group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          role="status"
          aria-live="polite"
          tabIndex={0}
        >
          <span
            aria-hidden
            className={cn("size-2 shrink-0 rounded-full", healthy ? "bg-success" : isError ? "bg-destructive" : "bg-warning")}
          />
          <span className="truncate group-data-[collapsible=icon]:hidden">{label}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-64 text-[12px]">
        {data ? (
          <div className="space-y-0.5">
            <p>Generator: {data.llm_model}</p>
            <p>Judge: {data.judge_model}</p>
            <p>Embeddings: {data.embedding_model}</p>
            <p>Reranker: {data.reranker_model}</p>
            <p className="tabular-nums">{data.chunk_count.toLocaleString()} chunks indexed</p>
          </div>
        ) : (
          <p>Start the API with `make api` on port 8102.</p>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
