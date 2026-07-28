from __future__ import annotations

import pytest

from retrieval_lab.container import Container
from retrieval_lab.errors import IndexMismatchError
from retrieval_lab.ingest.embedder import HashingEmbedder
from retrieval_lab.ingest.loader import load_corpus
from retrieval_lab.retrieval.components import IndexGuard
from retrieval_lab.retrieval.config import (
    Bm25Pipeline,
    DensePipeline,
    GenerationSettings,
    HybridPipeline,
    HybridRerankPipeline,
    QueryRewrite,
)

pytestmark = pytest.mark.db

QUESTION = "two Senators from each State, chosen by the legislature, for six years"


async def test_reingest_skips_unchanged_documents(container: Container) -> None:
    report = await container.ingest.ingest(load_corpus(container.settings.corpus_dir))
    assert all(doc.skipped for doc in report.documents)


@pytest.mark.parametrize(
    ("spec", "stages"),
    [
        (Bm25Pipeline(top_k=5), {"bm25"}),
        (DensePipeline(top_k=5), {"embed", "dense"}),
        (HybridPipeline(top_k=5), {"bm25", "embed", "dense", "fusion"}),
        (HybridRerankPipeline(top_k=5, rerank_candidates=10), {"bm25", "dense", "fusion", "rerank"}),
    ],
)
async def test_each_pipeline_finds_the_senate_clause(
    container: Container,
    spec: Bm25Pipeline | DensePipeline | HybridPipeline | HybridRerankPipeline,
    stages: set[str],
) -> None:
    outcome = await container.pipeline(spec).retrieve(QUESTION)
    assert len(outcome.chunks) == 5
    assert stages <= outcome.timings_ms.keys()
    assert any("two Senators from each State" in c.content for c in outcome.chunks)
    assert [c.rank for c in outcome.chunks] == [1, 2, 3, 4, 5]
    assert all(0.0 <= c.evidence_score <= 1.0 for c in outcome.chunks)


async def test_hybrid_records_ranks_from_every_stage(container: Container) -> None:
    outcome = await container.pipeline(HybridRerankPipeline(top_k=3, rerank_candidates=10)).retrieve(QUESTION)
    top = outcome.chunks[0]
    assert "rerank" in top.stage_ranks and "rrf" in top.stage_ranks
    assert top.stage_ranks["rerank"] == 1


async def test_query_rewrite_is_recorded_with_usage(container: Container) -> None:
    spec = HybridPipeline(top_k=3, query_rewrite=QueryRewrite(apply_to="bm25"))
    outcome = await container.pipeline(spec).retrieve("How old must a senator be?")
    assert outcome.rewritten_query is not None
    assert "age" in outcome.rewritten_query
    assert outcome.usage["rewrite"].input_tokens > 0


async def test_answer_cites_and_abstains(container: Container) -> None:
    pipeline = container.pipeline(HybridRerankPipeline(generation=GenerationSettings(abstain_below=0.2)))
    answered = await container.answers.answer(QUESTION, pipeline)
    assert not answered.answer.abstained
    assert answered.answer.citations
    assert "generate" in answered.timings_ms

    declined = await container.answers.answer(
        "Which programming language did Guido van Rossum create?", pipeline
    )
    assert declined.answer.abstained
    assert declined.answer.abstain_reason in {"low_evidence", "model_declined", "no_results"}


async def test_index_mismatch_is_detected(container: Container) -> None:
    await IndexGuard(container.sessions, container.embedder).check()
    with pytest.raises(IndexMismatchError):
        await IndexGuard(container.sessions, HashingEmbedder(128)).check()
