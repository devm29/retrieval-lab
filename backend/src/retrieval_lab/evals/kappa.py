from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Sequence


def confusion_matrix(
    rater_a: Sequence[Hashable], rater_b: Sequence[Hashable]
) -> dict[tuple[Hashable, Hashable], int]:
    if len(rater_a) != len(rater_b):
        raise ValueError("raters must label the same number of items")
    return dict(Counter(zip(rater_a, rater_b, strict=True)))


def percent_agreement(rater_a: Sequence[Hashable], rater_b: Sequence[Hashable]) -> float:
    if len(rater_a) != len(rater_b):
        raise ValueError("raters must label the same number of items")
    if not rater_a:
        return 0.0
    return sum(a == b for a, b in zip(rater_a, rater_b, strict=True)) / len(rater_a)


def cohens_kappa(rater_a: Sequence[Hashable], rater_b: Sequence[Hashable]) -> float:
    """Agreement between two raters corrected for chance: (p_o - p_e) / (1 - p_e)."""
    if len(rater_a) != len(rater_b):
        raise ValueError("raters must label the same number of items")
    n = len(rater_a)
    if n == 0:
        raise ValueError("kappa is undefined for zero items")
    observed = percent_agreement(rater_a, rater_b)
    counts_a = Counter(rater_a)
    counts_b = Counter(rater_b)
    expected = sum(counts_a[label] * counts_b[label] for label in counts_a.keys() | counts_b.keys()) / n**2
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def interpret_kappa(kappa: float) -> str:
    """Landis & Koch (1977) bands."""
    if kappa < 0:
        return "poor"
    for upper, label in ((0.2, "slight"), (0.4, "fair"), (0.6, "moderate"), (0.8, "substantial")):
        if kappa <= upper:
            return label
    return "almost perfect"
