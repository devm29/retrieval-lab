"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

const subscribe = () => () => undefined;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribe, () => true, () => false);

  return (
    <ToggleGroup
      type="single"
      aria-label="Appearance"
      value={mounted ? (theme ?? "system") : ""}
      onValueChange={(next) => {
        if (next) setTheme(next);
      }}
      spacing={0}
      className="flex h-8 w-full items-center rounded-lg bg-sidebar-accent/60 p-0.5 group-data-[collapsible=icon]:hidden"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <ToggleGroupItem
          key={value}
          value={value}
          aria-label={label}
          className="h-7 flex-1 rounded-md text-muted-foreground transition-colors duration-150 ease-apple hover:bg-transparent hover:text-foreground focus-visible:ring-4 focus-visible:ring-ring data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm"
        >
          <Icon className="size-4" strokeWidth={1.75} aria-hidden />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
