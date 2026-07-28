from __future__ import annotations

import pytest

from retrieval_lab.bootstrap import sync_configs
from retrieval_lab.container import Container
from retrieval_lab.db.models import RunStatus
from retrieval_lab.errors import ProviderError
from retrieval_lab.evals.baseline import compare
from retrieval_lab.evals.judge import Judge, RelevanceJudgement
from retrieval_lab.evals.runner import EvalRunner
from retrieval_lab.evals.schemas import GateTolerance, QuestionResult
from retrieval_lab.repositories.runs import RunRepository
from retrieval_lab.retrieval.config import PipelineConfig

pytestmark = pytest.mark.db


async def test_full_eval_scores_every_accepted_question(container: Container) -> None:
    run, summary = await container.runner.run("hybrid-rerank", trigger="cli")
    assert summary.question_count == 62
    assert summary.unanswerable_count == 6
    metrics = summary.metrics
    for value in (metrics.recall_at_k, metrics.mrr, metrics.ndcg_at_k, metrics.faithfulness):
        assert value is not None and 0.0 <= value <= 1.0
    assert metrics.ndcg_at_k is not None and metrics.ndcg_at_k > 0.3
    assert {"retrieval", "generate", "total"} <= summary.latency_ms.keys()
    assert "judge" in summary.cost

    async with container.sessions() as session:
        stored = await RunRepository(session).all_results(run.id)
    assert len(stored) == 62
    sample = QuestionResult.model_validate(stored[0].payload)
    assert sample.timings_ms["total"] > 0


async def test_retrieval_only_runs_skip_generation_metrics(container: Container) -> None:
    _, summary = await container.runner.run("bm25", mode="retrieval", trigger="cli")
    assert summary.metrics.faithfulness is None
    assert summary.metrics.ndcg_at_k is not None
    assert "generate" not in summary.latency_ms


async def test_eval_cutoff_controls_retrieval_depth(container: Container) -> None:
    run, deep = await container.runner.run("hybrid-rerank", mode="retrieval", trigger="cli", k=40)
    assert deep.k == 40
    async with container.sessions() as session:
        rows = await RunRepository(session).all_results(run.id)
    stored = [QuestionResult.model_validate(r.payload) for r in rows]
    assert max(len(r.retrieved) for r in stored) == 40
    _, shallow = await container.runner.run("hybrid-rerank", mode="retrieval", trigger="cli", k=3)
    assert (shallow.metrics.recall_at_k or 0) < (deep.metrics.recall_at_k or 0)


async def test_gate_catches_a_shallower_hnsw_search(container: Container) -> None:
    shallow = PipelineConfig.model_validate(
        {"name": "dense-shallow", "spec": {"kind": "dense", "top_k": 10, "ef_search": 10}}
    )
    await sync_configs(container, [shallow])
    _, baseline = await container.runner.run("dense", trigger="cli")
    _, candidate = await container.runner.run("dense-shallow", trigger="cli")
    result = compare(baseline, candidate, GateTolerance(ndcg_at_k=0.0), config_name="dense-shallow")
    assert not result.passed
    assert result.comparable
    assert compare(baseline, baseline, GateTolerance(), config_name="dense").passed


async def test_a_failing_question_fails_the_run_and_stops_the_rest(container: Container) -> None:
    calls = 0

    class BrokenJudge(Judge):
        async def relevance(self, question: str, answer: str) -> RelevanceJudgement:
            nonlocal calls
            calls += 1
            raise ProviderError("judge is down")

    runner = EvalRunner(
        container.sessions,
        container.pipeline,
        container.answers,
        BrokenJudge(container.judge_llm),
        container.index_guard,
        llm_model=container.llm.model,
        embedding_model=container.embedder.model_name,
        reranker_model=container.cross_encoder.model_name,
        concurrency=2,
    )
    run = await runner.start("bm25", trigger="cli")
    with pytest.raises(ExceptionGroup):
        await runner.execute(run.id)
    async with container.sessions() as session:
        failed = await RunRepository(session).get(run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error is not None and "judge is down" in failed.error
    assert calls < failed.question_count
