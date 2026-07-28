import { cn } from "@/lib/utils";

const CONTEXT_CHARS = 220;

function clean(text: string): string {
  return text.replace(/^#{1,6}\s+/gm, "").replace(/\*([^*\n]+)\*/g, "$1");
}

/** Cuts `text` to roughly `limit` characters at a word boundary, from the start or from the end. */
function trimToWords(text: string, limit: number, from: "start" | "end"): string {
  if (text.length <= limit) return text;
  if (from === "end") {
    const tail = text.slice(-limit);
    const space = tail.indexOf(" ");
    return `…${space === -1 ? tail : tail.slice(space + 1)}`;
  }
  const head = text.slice(0, limit);
  const space = head.lastIndexOf(" ");
  return `${space === -1 ? head : head.slice(0, space)}…`;
}

/**
 * Renders chunk text, marking the gold evidence span. Offsets index the raw text, so slice before
 * cleaning. When clamped, a highlighted chunk shows a window around the mark rather than its first
 * lines, so the evidence is never cut off.
 */
export function ChunkText({
  content,
  highlight,
  className,
  clamp,
}: {
  content: string;
  highlight?: readonly [number, number] | null;
  className?: string;
  clamp?: boolean;
}) {
  const base = cn("text-[14px] leading-[21px] whitespace-pre-line text-foreground/90", className);
  if (!highlight) return <p className={cn(base, clamp && "line-clamp-6")}>{clean(content)}</p>;
  const [start, end] = highlight;
  const before = content.slice(0, start);
  const after = content.slice(end);
  return (
    <p className={base}>
      {clean(clamp ? trimToWords(before, CONTEXT_CHARS, "end") : before)}
      <mark className="rounded bg-highlight px-0.5 text-foreground">{clean(content.slice(start, end))}</mark>
      {clean(clamp ? trimToWords(after, CONTEXT_CHARS, "start") : after)}
    </p>
  );
}
