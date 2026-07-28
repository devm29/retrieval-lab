from retrieval_lab.evals.baseline import compare
from retrieval_lab.evals.schemas import AggregateMetrics, GateTolerance, RunEnvironment, RunSummary


def _summary(**metrics: float | None) -> RunSummary:
    return RunSummary(
        k=10,
        mode="full",
        question_count=10,
        answerable_count=9,
        unanswerable_count=1,
        metrics=AggregateMetrics(**metrics),
        latency_ms={},
        cost={},
        total_cost_usd=0.0,
        cost_per_query_usd=0.0,
    )


BASE = _summary(ndcg_at_k=0.80, faithfulness=0.95, recall_at_k=0.9)


def test_small_drop_within_tolerance_passes() -> None:
    result = compare(
        BASE, _summary(ndcg_at_k=0.79, faithfulness=0.93, recall_at_k=0.5), GateTolerance(), config_name="c"
    )
    assert result.passed
    recall = next(d for d in result.deltas if d.metric == "recall_at_k")
    assert recall.tolerance is None and not recall.regressed


def test_ndcg_drop_beyond_tolerance_fails() -> None:
    result = compare(BASE, _summary(ndcg_at_k=0.75, faithfulness=0.95), GateTolerance(), config_name="c")
    assert not result.passed
    assert [d.metric for d in result.deltas if d.regressed] == ["ndcg_at_k"]


def test_faithfulness_drop_fails() -> None:
    result = compare(BASE, _summary(ndcg_at_k=0.9, faithfulness=0.90), GateTolerance(), config_name="c")
    assert [d.metric for d in result.deltas if d.regressed] == ["faithfulness"]


def test_improvements_pass() -> None:
    assert compare(BASE, _summary(ndcg_at_k=0.95, faithfulness=1.0), GateTolerance(), config_name="c").passed


def test_missing_gated_metric_fails_closed() -> None:
    result = compare(BASE, _summary(ndcg_at_k=0.9, faithfulness=None), GateTolerance(), config_name="c")
    assert not result.passed


def test_drop_exactly_at_tolerance_passes() -> None:
    tolerance = GateTolerance(ndcg_at_k=0.05, faithfulness=0.05)
    assert compare(BASE, _summary(ndcg_at_k=0.75, faithfulness=0.90), tolerance, config_name="c").passed


def _env(**changes: str) -> RunEnvironment:
    base = {
        "llm_model": "fake-extractive-v1",
        "judge_model": "fake-judge-v1",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "reranker_model": "Xenova/ms-marco-MiniLM-L-6-v2",
        "golden_hash": "a" * 64,
    }
    return RunEnvironment.model_validate({**base, **changes})


def test_same_environment_has_no_drift() -> None:
    before = BASE.model_copy(update={"environment": _env()})
    result = compare(before, before, GateTolerance(), config_name="c", spec_hashes=("x", "x"))
    assert result.drift == [] and result.comparable


def test_changed_golden_set_or_embedder_is_blocking_drift() -> None:
    before = BASE.model_copy(update={"environment": _env()})
    after = BASE.model_copy(update={"environment": _env(golden_hash="b" * 64, embedding_model="hashing-384")})
    result = compare(before, after, GateTolerance(), config_name="c")
    assert result.passed and not result.comparable
    assert result.model_dump(mode="json")["comparable"] is False
    assert {d.field for d in result.drift if d.blocking} == {"golden_hash", "embedding_model"}


def test_spec_change_and_missing_environment() -> None:
    before = BASE.model_copy(update={"environment": _env()})
    changed = compare(before, before, GateTolerance(), config_name="c", spec_hashes=("old", "new"))
    assert changed.comparable and [d.field for d in changed.drift] == ["spec_hash"]
    assert not compare(BASE, before, GateTolerance(), config_name="c").comparable


def test_different_k_is_not_comparable() -> None:
    before = BASE.model_copy(update={"environment": _env()})
    after = before.model_copy(update={"k": 20})
    assert not compare(before, after, GateTolerance(), config_name="c").comparable
