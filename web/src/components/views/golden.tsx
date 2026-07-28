"use client";

import { BookCheck, Inbox } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/metrics/segmented";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/metrics/states";
import { QuestionEditor } from "@/components/golden/question-editor";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import type { GoldenQuestion, GoldenStatus } from "@/lib/api/schemas";
import { useGolden, useSynthesize } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

export function GoldenView() {
  const [status, setStatus] = useState<GoldenStatus>("proposed");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const golden = useGolden(status, page);
  const totalPages = golden.data ? Math.max(1, Math.ceil(golden.data.total / golden.data.page_size)) : 1;
  const synthesize = useSynthesize();
  const items = golden.data?.items ?? [];
  const counts = golden.data?.counts ?? {};
  const selected = items.find((q) => q.id === selectedId) ?? items[0] ?? null;

  const listRef = useRef<HTMLUListElement>(null);

  const move = (offset: number) => {
    if (!selected) return;
    const index = items.findIndex((q) => q.id === selected.id);
    const next = items[Math.min(Math.max(index + offset, 0), items.length - 1)];
    if (!next) return;
    setSelectedId(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-question-id="${next.id}"]`)?.focus();
  };

  const afterDecision = () => {
    if (!selected) return;
    const index = items.findIndex((q) => q.id === selected.id);
    setSelectedId(items[index + 1]?.id ?? items[index - 1]?.id ?? null);
  };

  return (
    <Page
      title="Golden set"
      subtitle="The questions every run is scored against. Review synthetic proposals before they count."
      width="wide"
      actions={
        <Button
          variant="secondary"
          disabled={synthesize.isPending}
          onClick={() =>
            synthesize.mutate(5, {
              onSuccess: (r) => {
                toast.success(`${r.created} new questions to review`);
                setStatus("proposed");
              },
              onError: (e) => toast.error(e.message),
            })
          }
        >
          {synthesize.isPending ? "Generating…" : "Generate questions"}
        </Button>
      }
    >
      <div className="mb-5">
        <Segmented<GoldenStatus>
          label="Question status"
          value={status}
          onValueChange={(next) => {
            setStatus(next);
            setSelectedId(null);
            setPage(1);
          }}
          options={[
            { value: "proposed", label: `To review ${counts.proposed ?? ""}`.trim() },
            { value: "accepted", label: `Accepted ${counts.accepted ?? ""}`.trim() },
            { value: "rejected", label: `Rejected ${counts.rejected ?? ""}`.trim() },
          ]}
        />
      </div>

      {golden.isError ? <ErrorState error={golden.error} onRetry={() => void golden.refetch()} /> : null}
      {golden.isPending ? (
        <TableSkeleton rows={8} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={status === "proposed" ? Inbox : BookCheck}
          title={status === "proposed" ? "The review queue is clear" : `No ${status} questions`}
          description={
            status === "proposed"
              ? "Generate synthetic questions from random passages, then accept, edit or reject each one."
              : "Questions you review will show up here."
          }
          action={
            status === "proposed" ? (
              <Button onClick={() => synthesize.mutate(5)} disabled={synthesize.isPending}>
                Generate questions
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid overflow-hidden rounded-xl bg-card shadow-xs ring-1 ring-border/70 lg:grid-cols-[340px_1fr]">
          <div className="flex flex-col border-b border-border/60 lg:border-r lg:border-b-0">
          <ul
            ref={listRef}
            aria-label="Questions"
            aria-keyshortcuts="ArrowDown ArrowUp J K"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "j") {
                e.preventDefault();
                move(1);
              } else if (e.key === "ArrowUp" || e.key === "k") {
                e.preventDefault();
                move(-1);
              }
            }}
            className="max-h-[70vh] flex-1 divide-y divide-border/60 overflow-y-auto"
          >
            {items.map((q) => (
              <QuestionRow key={q.id} question={q} active={selected?.id === q.id} onSelect={() => setSelectedId(q.id)} />
            ))}
          </ul>
          {totalPages > 1 ? (
            <div className="flex items-center justify-between border-t border-border/60 px-4 py-2 text-[12px]">
              <span className="text-muted-foreground tabular-nums">
                {page} / {totalPages}
              </span>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  Next
                </Button>
              </div>
            </div>
          ) : null}
          </div>
          <div className="p-6">
            {selected ? <QuestionEditor key={selected.id} question={selected} onDone={afterDecision} /> : null}
          </div>
        </div>
      )}
    </Page>
  );
}

function QuestionRow({ question, active, onSelect }: { question: GoldenQuestion; active: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        data-question-id={question.id}
        aria-current={active ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "w-full px-4 py-3 text-left transition-colors duration-150 outline-none hover:bg-accent/50 focus-visible:bg-accent focus-visible:ring-4 focus-visible:ring-ring focus-visible:ring-inset",
          active && "bg-primary/10 hover:bg-primary/10",
        )}
      >
        <p className="line-clamp-2 text-[14px] font-medium">{question.question}</p>
        <p className="mt-0.5 truncate text-[12px] text-muted-foreground">
          {question.external_id ?? question.origin} · {question.document_slug ?? "unanswerable"}
        </p>
      </button>
    </li>
  );
}
