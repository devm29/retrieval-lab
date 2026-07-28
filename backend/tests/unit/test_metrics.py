import pytest

from retrieval_lab.evals import metrics
from retrieval_lab.evals.metrics import Span

EVIDENCE = [Span("doc", 100, 200)]


def test_coverage_merges_overlapping_chunks() -> None:
    chunks = [Span("doc", 50, 150), Span("doc", 120, 180)]
    assert metrics.coverage(EVIDENCE, chunks) == pytest.approx(0.8)


def test_coverage_ignores_other_documents() -> None:
    assert metrics.coverage(EVIDENCE, [Span("other", 0, 1000)]) == 0.0


def test_recall_at_k_respects_cutoff() -> None:
    ranked = [Span("doc", 0, 50), Span("doc", 90, 210)]
    assert metrics.recall_at_k(EVIDENCE, ranked, 1) == 0.0
    assert metrics.recall_at_k(EVIDENCE, ranked, 2) == 1.0


def test_ndcg_is_one_when_best_chunk_is_first() -> None:
    best = Span("doc", 90, 210)
    pool = [best, Span("doc", 150, 300)]
    assert metrics.ndcg_at_k(EVIDENCE, [best, Span("doc", 500, 600)], pool, 5) == pytest.approx(1.0)


def test_ndcg_does_not_double_count_overlapping_chunks() -> None:
    a, b = Span("doc", 90, 210), Span("doc", 80, 220)
    assert metrics.ndcg_at_k(EVIDENCE, [a, b], [a, b], 5) == pytest.approx(1.0)


def test_ndcg_discounts_late_hits() -> None:
    best = Span("doc", 90, 210)
    ranked = [Span("doc", 500, 600), Span("doc", 700, 800), best]
    assert metrics.ndcg_at_k(EVIDENCE, ranked, [best], 5) == pytest.approx(0.5)


def test_reciprocal_rank_uses_relevance_threshold() -> None:
    partial = Span("doc", 180, 260)  # covers 20% of the evidence
    full = Span("doc", 100, 200)
    assert metrics.reciprocal_rank(EVIDENCE, [partial, full], 5) == pytest.approx(0.5)
    assert metrics.reciprocal_rank(EVIDENCE, [partial], 5) == 0.0


def test_average_precision() -> None:
    assert metrics.average_precision([True, False, True]) == pytest.approx((1 + 2 / 3) / 2)
    assert metrics.average_precision([False, True]) == pytest.approx(0.5)
    assert metrics.average_precision([False, False]) == 0.0
    assert metrics.average_precision([]) == 0.0


@pytest.mark.parametrize(("q", "expected"), [(0.0, 1.0), (0.5, 2.5), (0.95, 3.85), (1.0, 4.0)])
def test_percentile_interpolates(q: float, expected: float) -> None:
    assert metrics.percentile([4.0, 1.0, 3.0, 2.0], q) == pytest.approx(expected)


def test_percentile_of_empty_is_zero() -> None:
    assert metrics.percentile([], 0.5) == 0.0
