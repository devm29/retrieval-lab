from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_lab.ingest.embedder import Embedder
from retrieval_lab.llm.base import LLMProvider, TokenUsage
from retrieval_lab.repositories.chunks import ChunkRepository, ChunkView
from retrieval_lab.retrieval.components import (
    Bm25Retriever,
    Candidate,
    DenseRetriever,
    QueryRewriter,
    Reranker,
    RrfFusion,
    StageClock,
)
from retrieval_lab.retrieval.config import (
    AnyPipeline,
    Bm25Pipeline,
    DensePipeline,
    HybridPipeline,
    HybridRerankPipeline,
)
from retrieval_lab.retrieval.rerank import CrossEncoder
from retrieval_lab.retrieval.types import RetrievalOutcome, RetrievedChunk


@dataclass(frozen=True, slots=True)
class _Ranked:
    candidates: list[Candidate]
    evidence: dict[str, float]
    stage_scores: dict[str, dict[str, float]]
    stage_ranks: dict[str, dict[str, int]]


def _ranks(candidates: Sequence[Candidate]) -> dict[str, int]:
    return {c.chunk_id: rank for rank, c in enumerate(candidates, start=1)}


def _scores(candidates: Sequence[Candidate]) -> dict[str, float]:
    return {c.chunk_id: c.score for c in candidates}


def _evidence(candidates: Sequence[Candidate]) -> dict[str, float]:
    return {c.chunk_id: c.evidence for c in candidates if c.evidence is not None}


class RetrievalPipeline:
    """Runs one pipeline spec: optional rewrite, then BM25 and/or dense, RRF, rerank."""

    def __init__(
        self,
        spec: AnyPipeline,
        *,
        sessions: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        cross_encoder: CrossEncoder,
        llm: LLMProvider,
    ) -> None:
        self.spec = spec
        self._sessions = sessions
        self._bm25 = Bm25Retriever(sessions)
        self._dense = DenseRetriever(sessions, embedder, getattr(spec, "ef_search", 80))
        self._reranker = Reranker(cross_encoder)
        self._rewriter = QueryRewriter(llm)

    async def retrieve(self, question: str, *, top_k: int | None = None) -> RetrievalOutcome:
        clock = StageClock()
        usage: dict[str, TokenUsage] = {}
        k = top_k or self.spec.top_k

        rewritten: str | None = None
        if self.spec.query_rewrite is not None:
            rewritten, usage["rewrite"] = await self._rewriter.rewrite(question, clock)
        rewrite = self.spec.query_rewrite
        apply_to = rewrite.apply_to if rewrite else None
        lexical_query = rewritten if rewritten and apply_to in {"bm25", "both"} else question
        semantic_query = rewritten if rewritten and apply_to in {"dense", "both"} else question
        rerank_query = (
            rewritten if rewritten and rewrite and rewrite.rerank_query == "rewritten" else question
        )

        with clock.stage("retrieval"):
            ranked = await self._rank(lexical_query, semantic_query, rerank_query, k, clock)

        top = ranked.candidates[:k]
        async with self._sessions() as session:
            views = await ChunkRepository(session).fetch([c.chunk_id for c in top])
        chunks = [
            self._to_chunk(rank, candidate, views[candidate.chunk_id], ranked)
            for rank, candidate in enumerate(top, start=1)
            if candidate.chunk_id in views
        ]
        return RetrievalOutcome(
            query=question,
            rewritten_query=rewritten,
            chunks=chunks,
            timings_ms=clock.timings_ms,
            usage=usage,
        )

    async def _rank(
        self, lexical_query: str, semantic_query: str, rerank_query: str, k: int, clock: StageClock
    ) -> _Ranked:
        spec = self.spec
        match spec:
            case Bm25Pipeline():
                hits = await self._bm25.search(lexical_query, k, clock)
                return _Ranked(hits, _evidence(hits), {"bm25": _scores(hits)}, {"bm25": _ranks(hits)})
            case DensePipeline():
                hits = await self._dense.search(semantic_query, k, clock)
                return _Ranked(hits, _evidence(hits), {"dense": _scores(hits)}, {"dense": _ranks(hits)})
            case HybridPipeline() | HybridRerankPipeline():
                return await self._hybrid(spec, lexical_query, semantic_query, rerank_query, k, clock)

    async def _hybrid(
        self,
        spec: HybridPipeline | HybridRerankPipeline,
        lexical_query: str,
        semantic_query: str,
        rerank_query: str,
        k: int,
        clock: StageClock,
    ) -> _Ranked:
        # An eval cut-off deeper than the spec's candidate depths widens them, so @k really sees k chunks.
        async def dense_branch() -> tuple[list[float], list[Candidate]]:
            vector = await self._dense.embed(semantic_query, clock)
            return vector, await self._dense.search_vector(vector, max(spec.dense_k, k), clock)

        bm25_hits, (vector, dense_hits) = await asyncio.gather(
            self._bm25.search(lexical_query, max(spec.bm25_k, k), clock), dense_branch()
        )
        fusion = RrfFusion(spec.rrf_k, {"bm25": spec.bm25_weight, "dense": spec.dense_weight})
        fused = fusion.fuse({"bm25": bm25_hits, "dense": dense_hits}, clock)
        stage_scores = {"bm25": _scores(bm25_hits), "dense": _scores(dense_hits), "rrf": _scores(fused)}
        stage_ranks = {"bm25": _ranks(bm25_hits), "dense": _ranks(dense_hits), "rrf": _ranks(fused)}

        if isinstance(spec, HybridRerankPipeline):
            pool = fused[: max(spec.rerank_candidates, k)]
            async with self._sessions() as session:
                views = await ChunkRepository(session).fetch([c.chunk_id for c in pool])
            ordered: list[ChunkView] = [views[c.chunk_id] for c in pool if c.chunk_id in views]
            reranked = await self._reranker.rerank(rerank_query, ordered, clock)
            stage_scores["rerank"] = _scores(reranked)
            stage_ranks["rerank"] = _ranks(reranked)
            return _Ranked(reranked, _evidence(reranked), stage_scores, stage_ranks)

        # RRF scores are rank-based, so cosine similarity is the calibrated signal for abstention.
        head = fused[:k]
        similarities = dict(stage_scores["dense"])
        missing = [c.chunk_id for c in head if c.chunk_id not in similarities]
        similarities.update(await self._dense.similarities(vector, missing))
        return _Ranked(fused, similarities, stage_scores, stage_ranks)

    @staticmethod
    def _to_chunk(rank: int, candidate: Candidate, view: ChunkView, ranked: _Ranked) -> RetrievedChunk:
        cid = candidate.chunk_id
        return RetrievedChunk(
            chunk_id=cid,
            rank=rank,
            document_slug=view.document_slug,
            document_title=view.document_title,
            heading=view.heading,
            content=view.content,
            char_start=view.char_start,
            char_end=view.char_end,
            score=candidate.score,
            evidence_score=max(0.0, min(1.0, ranked.evidence.get(cid, 0.0))),
            stage_scores={stage: s[cid] for stage, s in ranked.stage_scores.items() if cid in s},
            stage_ranks={stage: r[cid] for stage, r in ranked.stage_ranks.items() if cid in r},
        )
