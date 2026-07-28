"use client";

import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Pill } from "@/components/metrics/badges";
import { HistoryChart } from "@/components/metrics/charts";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/metrics/states";
import { Page, Section } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { PipelineConfig } from "@/lib/api/schemas";
import { useConfigHistory, useConfigs, useCreateConfig } from "@/lib/api/queries";
import { KIND_LABELS, ago } from "@/lib/format";
import { cn } from "@/lib/utils";

const specInput = z.record(z.string(), z.unknown());

export function ConfigsView() {
  const configs = useConfigs();
  const groups = new Map<string, PipelineConfig[]>();
  for (const config of configs.data ?? []) {
    groups.set(config.name, [...(groups.get(config.name) ?? []), config]);
  }
  const names = [...groups.keys()];
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const name = selectedName ?? names.find((n) => n === "hybrid-rerank") ?? names[0] ?? null;
  const versions = name ? (groups.get(name) ?? []) : [];
  const [versionId, setVersionId] = useState<string | null>(null);
  const version = versions.find((v) => v.id === versionId) ?? versions[0] ?? null;
  const [editing, setEditing] = useState(false);

  return (
    <Page
      title="Pipelines"
      subtitle="Retrieval configs are versioned by a hash of their spec. Change any parameter and you get a new version."
      width="wide"
      actions={
        version ? (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            New version
          </Button>
        ) : null
      }
    >
      {configs.isError ? <ErrorState error={configs.error} /> : null}
      {configs.isPending ? <TableSkeleton /> : null}
      {configs.data && names.length === 0 ? (
        <EmptyState icon={SlidersHorizontal} title="No pipeline configs" description="Run `rlab configs sync` to register the bundled configs." />
      ) : null}
      {version && name ? (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <nav aria-label="Configs" className="space-y-1">
            {names.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => {
                  setSelectedName(n);
                  setVersionId(null);
                }}
                className={cn(
                  "flex h-9 w-full items-center justify-between rounded-lg px-3 text-left text-[14px] transition-colors duration-150 outline-none hover:bg-accent/60 focus-visible:ring-4 focus-visible:ring-ring",
                  n === name && "bg-primary/10 font-medium hover:bg-primary/10",
                )}
              >
                <span className="truncate">{n}</span>
                <span className="text-[12px] text-muted-foreground tabular-nums">{groups.get(n)?.length} v</span>
              </button>
            ))}
          </nav>
          <div className="min-w-0 space-y-8">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {version.name}@{version.version}
                  {version.is_latest ? <Pill tone="blue">Latest</Pill> : null}
                </CardTitle>
                <CardDescription>
                  {KIND_LABELS[version.kind]} · hash <span className="font-mono">{version.spec_hash.slice(0, 12)}</span> ·
                  registered {ago(version.created_at)}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {version.description ? <p className="text-[14px]">{version.description}</p> : null}
                <div className="flex flex-wrap gap-2" role="tablist" aria-label="Versions">
                  {versions.map((v) => (
                    <button
                      key={v.id}
                      type="button"
                      role="tab"
                      aria-selected={v.id === version.id}
                      onClick={() => setVersionId(v.id)}
                      className={cn(
                        "h-7 rounded-full px-3 text-[13px] tabular-nums transition-colors duration-150 outline-none focus-visible:ring-4 focus-visible:ring-ring",
                        v.id === version.id ? "bg-primary text-primary-foreground" : "bg-secondary hover:bg-accent",
                      )}
                    >
                      v{v.version}
                    </button>
                  ))}
                </div>
                <pre className="overflow-x-auto rounded-lg bg-secondary p-4 font-mono text-[12px] leading-5">
                  {JSON.stringify(version.spec, null, 2)}
                </pre>
              </CardContent>
            </Card>
            <History name={name} />
          </div>
        </div>
      ) : null}
      {version ? <NewVersionDialog base={version} open={editing} onOpenChange={setEditing} /> : null}
    </Page>
  );
}

function History({ name }: { name: string }) {
  const history = useConfigHistory(name);
  return (
    <Section title="Quality over time" description="Every completed full run of this config, oldest first.">
      <div className="rounded-xl bg-card p-5 shadow-xs ring-1 ring-border/70">
        {history.data && history.data.length > 0 ? (
          <HistoryChart points={history.data} />
        ) : (
          <p className="text-[14px] text-muted-foreground">No completed runs yet.</p>
        )}
      </div>
    </Section>
  );
}

export function NewVersionDialog({
  base,
  open,
  onOpenChange,
}: {
  base: PipelineConfig;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(base.spec, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [seededFrom, setSeededFrom] = useState({ id: base.id, open });
  const create = useCreateConfig();

  // The parent opens the dialog without going through onOpenChange, so the editor is reseeded
  // from the selected config whenever it opens or the selection changes.
  if (seededFrom.id !== base.id || seededFrom.open !== open) {
    setSeededFrom({ id: base.id, open });
    if (open) {
      setText(JSON.stringify(base.spec, null, 2));
      setError(null);
    }
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setError("That isn't valid JSON. Check for trailing commas or missing quotes.");
      return;
    }
    const spec = specInput.safeParse(parsed);
    if (!spec.success) {
      setError("The spec must be a JSON object.");
      return;
    }
    setError(null);
    create.mutate(
      { name: base.name, description: base.description, spec: spec.data },
      {
        onSuccess: ({ config, created }) => {
          toast.success(created ? `Registered ${config.name}@${config.version}` : `Identical to ${config.name}@${config.version}`);
          onOpenChange(false);
        },
        onError: (e) => setError(e.message),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle className="text-[17px] font-semibold">New version of {base.name}</DialogTitle>
            <DialogDescription>
              Edit the spec. It is validated by the same Pydantic models the pipeline uses; unknown keys are rejected.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="spec" className="text-[13px] font-medium">
              Spec
            </Label>
            <Textarea
              id="spec"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={14}
              spellCheck={false}
              className="rounded-lg font-mono text-[12px]"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "spec-error" : undefined}
            />
            {error ? (
              <p id="spec-error" role="alert" className="text-[12px] text-destructive">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Register version
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
