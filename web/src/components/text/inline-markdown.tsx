import type { ReactNode } from "react";

// Corpus text is Markdown, so extractive answers and claims can carry *emphasis* or a heading
// marker. Only the inline subset is rendered; anything unpaired stays literal.
const EMPHASIS = /\*\*(\S(?:[^*\n]*?\S)?)\*\*|\*(\S(?:[^*\n]*?\S)?)\*/g;
const HEADING = /^#{1,6}\s+/gm;

export type LeafRenderer = (text: string, key: string) => ReactNode;

const plain: LeafRenderer = (text) => text;

export function renderInline(text: string, leaf: LeafRenderer = plain, keyPrefix = "md"): ReactNode[] {
  const source = text.replace(HEADING, "");
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of source.matchAll(EMPHASIS)) {
    const index = match.index;
    const key = `${keyPrefix}-${index}`;
    if (index > last) nodes.push(leaf(source.slice(last, index), `${key}-pre`));
    const [, strong, em] = match;
    nodes.push(
      strong !== undefined ? (
        <strong key={key} className="font-semibold">
          {leaf(strong, `${key}-in`)}
        </strong>
      ) : (
        <em key={key}>{leaf(em ?? "", `${key}-in`)}</em>
      ),
    );
    last = index + match[0].length;
  }
  if (last < source.length) nodes.push(leaf(source.slice(last), `${keyPrefix}-${last}-post`));
  return nodes;
}

export function InlineMarkdown({ text }: { text: string }) {
  return <>{renderInline(text)}</>;
}
