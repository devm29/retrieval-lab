import pytest

from retrieval_lab.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_scores_match_formula() -> None:
    fused = dict(reciprocal_rank_fusion({"bm25": ["a", "b"], "dense": ["b", "c"]}, k=60))
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["c"] == pytest.approx(1 / 62)


def test_rrf_orders_documents_found_by_both_lists_first() -> None:
    ranking = [doc for doc, _ in reciprocal_rank_fusion({"x": ["a", "b", "c"], "y": ["c", "d"]}, k=60)]
    assert ranking[0] == "c"


def test_rrf_weights_and_zero_weight_lists() -> None:
    fused = dict(reciprocal_rank_fusion({"x": ["a"], "y": ["b"]}, k=10, weights={"x": 2.0, "y": 0.0}))
    assert fused == {"a": pytest.approx(2 / 11)}


def test_rrf_ignores_duplicate_ids_within_a_list() -> None:
    fused = dict(reciprocal_rank_fusion({"x": ["a", "a", "b"]}, k=1))
    assert fused["b"] == pytest.approx(1 / 3)


def test_rrf_ties_are_stable() -> None:
    first = reciprocal_rank_fusion({"x": ["a"], "y": ["b"]}, k=60)
    assert [d for d, _ in first] == ["a", "b"]


def test_rrf_rejects_non_positive_k() -> None:
    with pytest.raises(ValueError, match="positive"):
        reciprocal_rank_fusion({"x": ["a"]}, k=0)
