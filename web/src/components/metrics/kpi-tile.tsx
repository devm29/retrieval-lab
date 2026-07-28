import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface KpiTileProps {
  label: string;
  value: string;
  hint?: string;
  delta?: { value: number; text: string; lowerIsBetter?: boolean } | null;
  footnote?: string;
  className?: string;
}

export function KpiTile({ label, value, hint, delta, footnote, className }: KpiTileProps) {
  const improved = delta ? (delta.lowerIsBetter ? delta.value < 0 : delta.value > 0) : false;
  const flat = !delta || Math.abs(delta.value) < 1e-9;

  return (
    <div className={cn("rounded-xl bg-card p-5 shadow-xs ring-1 ring-border/70", className)}>
      <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
        <span>{label}</span>
        {hint ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="relative rounded-full text-muted-foreground/80 outline-none after:absolute after:-inset-[7px] after:content-[''] hover:text-foreground focus-visible:ring-4 focus-visible:ring-ring pointer-coarse:after:-inset-[15px]"
                aria-label={`About ${label}`}
              >
                <Info className="size-3.5" strokeWidth={1.75} />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-60 text-[12px]">{hint}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>
      <p className="mt-1 text-[28px] leading-[34px] font-semibold tracking-tight tabular-nums">{value}</p>
      {delta && !flat ? (
        <p
          className={cn(
            "mt-1 flex items-center gap-0.5 text-[13px] tabular-nums",
            improved ? "text-success" : "text-destructive",
          )}
        >
          {delta.value > 0 ? (
            <ArrowUpRight className="size-3.5" strokeWidth={2} aria-hidden />
          ) : (
            <ArrowDownRight className="size-3.5" strokeWidth={2} aria-hidden />
          )}
          {delta.text}
          <span className="sr-only">{improved ? "better than baseline" : "worse than baseline"}</span>
        </p>
      ) : footnote ? (
        <p className="mt-1 text-[13px] text-muted-foreground">{footnote}</p>
      ) : null}
    </div>
  );
}
