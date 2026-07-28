from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,79}$"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QueryRewrite(_Frozen):
    apply_to: Literal["bm25", "dense", "both"] = "bm25"
    rerank_query: Literal["original", "rewritten"] = Field(
        default="original",
        description="Which query the cross-encoder scores passages against; only hybrid_rerank uses it.",
    )


class GenerationSettings(_Frozen):
    max_context_chunks: int = Field(default=5, ge=1, le=20)
    abstain_below: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Abstain when the top chunk's evidence score is below this value.",
    )
    max_output_tokens: int = Field(default=1024, ge=64, le=16000)


class _PipelineBase(_Frozen):
    top_k: int = Field(default=10, ge=1, le=50)
    query_rewrite: QueryRewrite | None = None
    generation: GenerationSettings = GenerationSettings()


class Bm25Pipeline(_PipelineBase):
    kind: Literal["bm25"] = "bm25"


class DensePipeline(_PipelineBase):
    kind: Literal["dense"] = "dense"
    ef_search: int = Field(default=80, ge=10, le=1000)


class _HybridBase(_PipelineBase):
    bm25_k: int = Field(default=50, ge=1, le=500)
    dense_k: int = Field(default=50, ge=1, le=500)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    bm25_weight: float = Field(default=1.0, ge=0.0)
    dense_weight: float = Field(default=1.0, ge=0.0)
    ef_search: int = Field(default=80, ge=10, le=1000)

    @model_validator(mode="after")
    def _has_weight(self) -> _HybridBase:
        if self.bm25_weight == 0 and self.dense_weight == 0:
            raise ValueError("at least one of bm25_weight and dense_weight must be positive")
        return self


class HybridPipeline(_HybridBase):
    kind: Literal["hybrid"] = "hybrid"


class HybridRerankPipeline(_HybridBase):
    kind: Literal["hybrid_rerank"] = "hybrid_rerank"
    rerank_candidates: int = Field(default=30, ge=1, le=200)

    @model_validator(mode="after")
    def _enough_candidates(self) -> HybridRerankPipeline:
        if self.rerank_candidates < self.top_k:
            raise ValueError("rerank_candidates must be at least top_k")
        return self


PipelineSpec = Annotated[
    Bm25Pipeline | DensePipeline | HybridPipeline | HybridRerankPipeline,
    Field(discriminator="kind"),
]


class PipelineConfig(_Frozen):
    name: str = Field(pattern=SLUG_PATTERN)
    description: str = ""
    spec: PipelineSpec

    @property
    def spec_hash(self) -> str:
        return spec_hash(self.spec)


AnyPipeline = Bm25Pipeline | DensePipeline | HybridPipeline | HybridRerankPipeline


def spec_hash(spec: AnyPipeline) -> str:
    canonical = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
