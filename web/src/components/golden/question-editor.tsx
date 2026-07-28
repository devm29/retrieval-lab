"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Pill } from "@/components/metrics/badges";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { GoldenQuestion, GoldenStatus } from "@/lib/api/schemas";
import { type GoldenPatch, useUpdateGolden } from "@/lib/api/queries";
import { ago } from "@/lib/format";

interface Draft {
  question: string;
  evidence: string;
  reference_answer: string;
}

function toDraft(q: GoldenQuestion): Draft {
  return { question: q.question, evidence: q.evidence ?? "", reference_answer: q.reference_answer ?? "" };
}

export function QuestionEditor({ question, onDone }: { question: GoldenQuestion; onDone: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(question));
  const update = useUpdateGolden();
  const dirty =
    draft.question !== question.question ||
    draft.evidence !== (question.evidence ?? "") ||
    draft.reference_answer !== (question.reference_answer ?? "");

  const save = (status?: GoldenStatus) => {
    const patch: GoldenPatch = {};
    if (draft.question !== question.question) patch.question = draft.question.trim();
    if (draft.evidence !== (question.evidence ?? "")) patch.evidence = draft.evidence.trim() || null;
    if (draft.reference_answer !== (question.reference_answer ?? "")) {
      patch.reference_answer = draft.reference_answer.trim() || null;
    }
    if (status) patch.status = status;
    update.mutate(
      { id: question.id, patch },
      {
        onSuccess: () => {
          toast.success(
            status === "accepted" ? "Added to the golden set" : status === "rejected" ? "Question rejected" : "Changes saved",
          );
          if (status) onDone();
        },
        onError: (error) => toast.error(error.message),
      },
    );
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!(event.metaKey || event.ctrlKey) || update.isPending) return;
    if (event.key === "Enter" && question.status !== "accepted") {
      event.preventDefault();
      save("accepted");
    } else if (event.key === "Backspace" && event.shiftKey && question.status !== "rejected") {
      event.preventDefault();
      save("rejected");
    }
  };

  return (
    <div className="space-y-5" onKeyDown={onKeyDown}>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
        <Pill tone={question.origin === "synthetic" ? "blue" : "neutral"}>{question.origin}</Pill>
        <span>{question.document_slug ?? "No source document"}</span>
        {question.source_chunk_id ? <span className="font-mono">{question.source_chunk_id}</span> : null}
        <span>· created {ago(question.created_at)}</span>
      </div>

      <div className="space-y-2">
        <Label htmlFor="g-question" className="text-[13px] font-medium">
          Question
        </Label>
        <Textarea
          id="g-question"
          value={draft.question}
          onChange={(e) => setDraft({ ...draft, question: e.target.value })}
          rows={2}
          className="resize-none rounded-lg text-[15px]"
        />
      </div>
      {question.answerable ? (
        <div className="space-y-2">
          <Label htmlFor="g-evidence" className="text-[13px] font-medium">
            Evidence quote
          </Label>
          <Textarea
            id="g-evidence"
            value={draft.evidence}
            onChange={(e) => setDraft({ ...draft, evidence: e.target.value })}
            rows={5}
            className="rounded-lg text-[14px]"
            aria-describedby="g-evidence-help"
          />
          <p id="g-evidence-help" className="text-[12px] text-muted-foreground">
            Must appear verbatim in {question.document_slug}. Metrics are scored against this span, so keep it as short as the
            answer allows.
          </p>
        </div>
      ) : (
        <p className="rounded-lg bg-secondary px-3 py-2 text-[13px] text-muted-foreground">
          Unanswerable by design: the right behaviour is to abstain.
        </p>
      )}
      <div className="space-y-2">
        <Label htmlFor="g-answer" className="text-[13px] font-medium">
          Reference answer <span className="font-normal text-muted-foreground">(optional)</span>
        </Label>
        <Textarea
          id="g-answer"
          value={draft.reference_answer}
          onChange={(e) => setDraft({ ...draft, reference_answer: e.target.value })}
          rows={2}
          className="resize-none rounded-lg text-[14px]"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
        {question.status !== "rejected" ? (
          <Button
            variant="ghost"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => save("rejected")}
            aria-keyshortcuts="Shift+Meta+Backspace"
            disabled={update.isPending}
          >
            <X className="size-4" aria-hidden /> Reject
            <kbd className="ml-1 hidden rounded bg-destructive/10 px-1 text-[11px] sm:inline">⇧⌘⌫</kbd>
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => save()} disabled={!dirty || update.isPending}>
            Save
          </Button>
          {question.status !== "accepted" ? (
            <Button onClick={() => save("accepted")} disabled={update.isPending} aria-keyshortcuts="Meta+Enter">
              <Check className="size-4" aria-hidden /> Accept
              <kbd className="ml-1 hidden rounded bg-primary-foreground/20 px-1 text-[11px] sm:inline">⌘↵</kbd>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
