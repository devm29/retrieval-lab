from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse ranked id lists: score(d) = sum_r w_r / (k + rank_r(d)), ranks 1-based.

    Ties are broken by the best individual rank, then by id, so output is stable.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for name, ids in rankings.items():
        weight = 1.0 if weights is None else weights.get(name, 1.0)
        if weight == 0:
            continue
        for rank, doc_id in enumerate(dict.fromkeys(ids), start=1):
            scores[doc_id] += weight / (k + rank)
            best_rank[doc_id] = min(best_rank.get(doc_id, rank), rank)
    return sorted(scores.items(), key=lambda item: (-item[1], best_rank[item[0]], item[0]))
