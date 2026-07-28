"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

interface SegmentedProps<T extends string> {
  value: T;
  onValueChange: (value: T) => void;
  options: readonly { value: T; label: React.ReactNode }[];
  label: string;
}

/** Apple-style segmented control: a single-choice radio group with arrow-key navigation. */
export function Segmented<T extends string>({ value, onValueChange, options, label }: SegmentedProps<T>) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(next) => {
        const match = options.find((o) => o.value === next);
        if (match) onValueChange(match.value);
      }}
      aria-label={label}
      spacing={0.5}
      className="h-8 rounded-lg bg-secondary p-0.5"
    >
      {options.map((option) => (
        <ToggleGroupItem
          key={option.value}
          value={option.value}
          size="sm"
          className="h-7 rounded-md px-3 text-[13px] font-normal text-muted-foreground hover:bg-transparent hover:text-foreground data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm focus-visible:ring-4 focus-visible:ring-ring"
        >
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
