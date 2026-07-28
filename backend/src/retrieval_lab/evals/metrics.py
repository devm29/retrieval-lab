"""Span-based IR metrics.

Golden questions point at evidence character spans in a document rather than at
chunk ids, so the same golden set scores any chunking strategy. A chunk's gain is
the share of evidence it covers that no higher-ranked chunk already covered, which
keeps overlapping chunks from being double counted.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

RELEVANCE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Span:
    doc: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _covered(evidence: Span, chunks: Sequence[Span]) -> int:
    clipped = [
        (max(c.start, evidence.start), min(c.end, evidence.end))
        for c in chunks
        if c.doc == evidence.doc and c.start < evidence.end and c.end > evidence.start
    ]
    return sum(end - start for start, end in _merge(clipped))


def coverage(evidence: Sequence[Span], chunks: Sequence[Span]) -> float:
    total = sum(e.length for e in evidence)
    if total == 0:
        return 0.0
    return sum(_covered(e, chunks) for e in evidence) / total


def is_relevant(evidence: Sequence[Span], chunk: Span, threshold: float = RELEVANCE_THRESHOLD) -> bool:
    return any(e.length and _covered(e, [chunk]) / e.length >= threshold for e in evidence)


def marginal_gains(evidence: Sequence[Span], ranked: Sequence[Span]) -> list[float]:
    gains: list[float] = []
    previous = 0.0
    for i in range(len(ranked)):
        current = coverage(evidence, ranked[: i + 1])
        gains.append(current - previous)
        previous = current
    return gains


def recall_at_k(evidence: Sequence[Span], ranked: Sequence[Span], k: int) -> float:
    return coverage(evidence, ranked[:k])


def _dcg(gains: Sequence[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ideal_ordering(evidence: Sequence[Span], pool: Sequence[Span], k: int) -> list[Span]:
    """Greedy max-marginal-coverage ordering; optimal for one contiguous evidence span."""
    remaining = list(pool)
    chosen: list[Span] = []
    while remaining and len(chosen) < k:
        base = coverage(evidence, chosen)
        best = max(remaining, key=lambda s: coverage(evidence, [*chosen, s]) - base)
        if coverage(evidence, [*chosen, best]) - base <= 0:
            break
        chosen.append(best)
        remaining.remove(best)
    return chosen


def ndcg_at_k(evidence: Sequence[Span], ranked: Sequence[Span], pool: Sequence[Span], k: int) -> float:
    ideal = _dcg(marginal_gains(evidence, ideal_ordering(evidence, pool, k)))
    if ideal == 0:
        return 0.0
    return min(1.0, _dcg(marginal_gains(evidence, ranked[:k])) / ideal)


def reciprocal_rank(evidence: Sequence[Span], ranked: Sequence[Span], k: int) -> float:
    for rank, chunk in enumerate(ranked[:k], start=1):
        if is_relevant(evidence, chunk):
            return 1.0 / rank
    return 0.0


def average_precision(relevant: Sequence[bool]) -> float:
    """Mean of precision@i over the ranks i that hold a relevant item; RAGAS context precision."""
    hits = 0
    total = 0.0
    for rank, flag in enumerate(relevant, start=1):
        if flag:
            hits += 1
            total += hits / rank
    return total / hits if hits else 0.0


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
