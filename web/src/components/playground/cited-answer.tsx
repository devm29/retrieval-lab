import { Fragment, type ReactNode } from "react";

import { renderInline } from "@/components/text/inline-markdown";
import { cn } from "@/lib/utils";

const MARKER = /\[(\d+(?:\s*[,;]\s*\d+)*)\]/g;

function renderMarkers(
  text: string,
  key: string,
  validMarkers: ReadonlySet<number>,
  onCite: (marker: number) => void,
): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const index = match.index;
    parts.push(text.slice(last, index));
    const markers = [...new Set((match[1] ?? "").split(/[,;]/).map((m) => Number(m.trim())))];
    parts.push(
      <Fragment key={`${index}-cite`}>
        {markers.map((marker) =>
          validMarkers.has(marker) ? (
            <button
              key={marker}
              type="button"
              onClick={() => onCite(marker)}
              className="relative mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[5px] bg-primary/12 px-1 align-[2px] text-[11px] font-semibold text-primary tabular-nums transition-colors duration-150 after:absolute after:-inset-[5px] after:content-[''] hover:bg-primary hover:text-primary-foreground focus-visible:ring-4 focus-visible:ring-ring focus-visible:outline-none pointer-coarse:after:-inset-[13px]"
              aria-label={`Source ${marker}`}
            >
              {marker}
            </button>
          ) : (
            <span key={marker} className="text-[11px] text-destructive" title="Citation does not match a source">
              [{marker}]
            </span>
          ),
        )}
      </Fragment>,
    );
    last = index + match[0].length;
  }
  parts.push(text.slice(last));
  return <Fragment key={key}>{parts}</Fragment>;
}

export function CitedAnswer({
  text,
  validMarkers,
  onCite,
  className,
}: {
  text: string;
  validMarkers: ReadonlySet<number>;
  onCite: (marker: number) => void;
  className?: string;
}) {
  return (
    <p className={cn("text-[17px] leading-[26px]", className)}>
      {renderInline(text, (segment, key) => renderMarkers(segment, key, validMarkers, onCite))}
    </p>
  );
}
