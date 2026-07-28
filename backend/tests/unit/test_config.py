import pytest
from pydantic import ValidationError

from retrieval_lab.retrieval.config import (
    Bm25Pipeline,
    HybridRerankPipeline,
    PipelineConfig,
    spec_hash,
)


def test_discriminated_union_parses_each_kind() -> None:
    config = PipelineConfig.model_validate(
        {"name": "xr", "spec": {"kind": "hybrid_rerank", "rerank_candidates": 20, "top_k": 5}}
    )
    assert isinstance(config.spec, HybridRerankPipeline)
    assert config.spec.rrf_k == 60


def test_hash_ignores_name_description_and_key_order() -> None:
    a = PipelineConfig.model_validate({"name": "aa", "spec": {"kind": "bm25", "top_k": 5}})
    b = PipelineConfig.model_validate(
        {"name": "bb", "description": "d", "spec": {"top_k": 5, "kind": "bm25"}}
    )
    assert a.spec_hash == b.spec_hash


def test_hash_changes_with_any_parameter() -> None:
    assert spec_hash(Bm25Pipeline(top_k=5)) != spec_hash(Bm25Pipeline(top_k=6))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PipelineConfig.model_validate({"name": "x", "spec": {"kind": "bm25", "topk": 5}})


def test_rerank_pool_must_cover_top_k() -> None:
    with pytest.raises(ValidationError, match="rerank_candidates"):
        HybridRerankPipeline(top_k=20, rerank_candidates=10)


def test_hybrid_needs_a_positive_weight() -> None:
    with pytest.raises(ValidationError, match="weight"):
        PipelineConfig.model_validate(
            {"name": "x", "spec": {"kind": "hybrid", "bm25_weight": 0, "dense_weight": 0}}
        )


def test_names_are_slugs() -> None:
    with pytest.raises(ValidationError):
        PipelineConfig.model_validate({"name": "Not A Slug", "spec": {"kind": "bm25"}})


def test_shipped_pipeline_files_are_valid() -> None:
    from retrieval_lab.bootstrap import load_pipeline_files
    from retrieval_lab.settings import PROJECT_ROOT

    configs = load_pipeline_files(PROJECT_ROOT / "data" / "pipelines")
    assert {c.name for c in configs} >= {"bm25", "dense", "hybrid-rrf", "hybrid-rerank"}
