import { AlertTriangle, type LucideIcon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl bg-card px-6 py-14 text-center ring-1 ring-border/70">
      <Icon className="size-11 text-muted-foreground/70" strokeWidth={1.25} aria-hidden />
      <h3 className="mt-4 text-[17px] font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-[14px] text-muted-foreground">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "We couldn't load this.",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl bg-destructive/8 p-4 text-[14px] ring-1 ring-destructive/20">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" strokeWidth={1.75} aria-hidden />
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        <p className="text-muted-foreground">{message}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry} className="rounded-sm text-primary outline-none hover:underline focus-visible:ring-4 focus-visible:ring-ring">
            Try again
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-border/70" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full rounded-md" />
      ))}
    </div>
  );
}

export function TilesSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className="h-[118px] rounded-xl" />
      ))}
    </div>
  );
}
