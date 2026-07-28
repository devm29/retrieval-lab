import { cn } from "@/lib/utils";

export function ScoreBar({ value, className, label }: { value: number | null; className?: string; label: string }) {
  const width = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={value ?? 0}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-secondary", className)}
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out-apple" style={{ width: `${width}%` }} />
    </div>
  );
}
