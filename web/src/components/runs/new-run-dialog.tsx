"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/metrics/segmented";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useConfigs, useStartRun } from "@/lib/api/queries";
import { configLabel } from "@/lib/format";

type Mode = "full" | "retrieval";

export function NewRunDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const configs = useConfigs();
  const start = useStartRun();
  const latest = (configs.data ?? []).filter((c) => c.is_latest);
  const [config, setConfig] = useState<string>("hybrid-rerank");
  const [mode, setMode] = useState<Mode>("full");
  const [label, setLabel] = useState("");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    start.mutate(
      { config, mode, ...(label.trim() ? { label: label.trim() } : {}) },
      {
        onSuccess: (run) => {
          toast.success(`Run started for ${configLabel(run.config)}`);
          onOpenChange(false);
          router.push(`/runs/${run.id}`);
        },
        onError: (error) => toast.error(error.message),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <form onSubmit={submit} className="space-y-5">
          <DialogHeader>
            <DialogTitle className="text-[17px] font-semibold">New evaluation run</DialogTitle>
            <DialogDescription>
              Scores the config against every accepted golden question. Offline runs take a few seconds.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="run-config" className="text-[13px] font-medium">
              Pipeline config
            </Label>
            <Select value={config} onValueChange={setConfig}>
              <SelectTrigger id="run-config" className="h-9 w-full rounded-lg">
                <SelectValue placeholder="Choose a config" />
              </SelectTrigger>
              <SelectContent>
                {latest.map((c) => (
                  <SelectItem key={c.id} value={c.name}>
                    {configLabel(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <p className="text-[13px] font-medium">
              What to measure
            </p>
            <Segmented<Mode>
              label="What to measure"
              value={mode}
              onValueChange={setMode}
              options={[
                { value: "full", label: "Retrieval + answers" },
                { value: "retrieval", label: "Retrieval only" },
              ]}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="run-label" className="text-[13px] font-medium">
              Label <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="run-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. after chunker change"
              maxLength={200}
              className="h-9 rounded-lg"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={start.isPending || !config}>
              {start.isPending ? "Starting…" : "Start run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
