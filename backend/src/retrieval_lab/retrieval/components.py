from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import NamedTuple, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_lab.db.session import transaction
from retrieval_lab.errors import IndexMismatchError
from retrieval_lab.ingest.embedder import Embedder
from retrieval_lab.llm.base import LLMProvider, LLMRequest, RewriteInputs, TokenUsage
from retrieval_lab.repositories.chunks import ChunkRepository, ChunkView
from retrieval_lab.retrieval.fusion import reciprocal_rank_fusion
from retrieval_lab.retrieval.rerank import CrossEncoder


class Candidate(NamedTuple):
    chunk_id: str
    score: float
    evidence: float | None = None


class StageClock:
    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self.timings_ms[name] = round(self.timings_ms.get(name, 0.0) + elapsed, 3)


class Retriever(Protocol):
    name: str

    async def search(self, query: str, k: int, clock: StageClock) -> list[Candidate]: ...


class Bm25Retriever:
    """Okapi BM25 computed in Postgres over the chunk tsvectors."""

    name = "bm25"

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, query: str, k: int, clock: StageClock) -> list[Candidate]:
        with clock.stage(self.name):
            async with self._sessions() as session:
                rows = await ChunkRepository(session).bm25(query, k)
        return [Candidate(chunk_id, score, share) for chunk_id, score, share in rows]


class DenseRetriever:
    name = "dense"

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, ef_search: int = 80
    ) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._ef_search = ef_search

    async def embed(self, query: str, clock: StageClock) -> list[float]:
        with clock.stage("embed"):
            return await self._embedder.embed_query(query)

    async def search_vector(self, vector: Sequence[float], k: int, clock: StageClock) -> list[Candidate]:
        with clock.stage(self.name):
            async with transaction(self._sessions) as session:
                rows = await ChunkRepository(session).dense(vector, k, self._ef_search)
        return [Candidate(chunk_id, score, score) for chunk_id, score in rows]

    async def search(self, query: str, k: int, clock: StageClock) -> list[Candidate]:
        return await self.search_vector(await self.embed(query, clock), k, clock)

    async def similarities(self, vector: Sequence[float], ids: Sequence[str]) -> dict[str, float]:
        async with self._sessions() as session:
            return await ChunkRepository(session).similarities(vector, ids)


class RrfFusion:
    def __init__(self, k: int, weights: dict[str, float]) -> None:
        self._k = k
        self._weights = weights

    def fuse(self, rankings: dict[str, list[Candidate]], clock: StageClock) -> list[Candidate]:
        with clock.stage("fusion"):
            fused = reciprocal_rank_fusion(
                {name: [c.chunk_id for c in ranked] for name, ranked in rankings.items()},
                k=self._k,
                weights=self._weights,
            )
        return [Candidate(chunk_id, score) for chunk_id, score in fused]


class Reranker:
    def __init__(self, encoder: CrossEncoder) -> None:
        self._encoder = encoder

    @property
    def model_name(self) -> str:
        return self._encoder.model_name

    async def rerank(self, query: str, chunks: Sequence[ChunkView], clock: StageClock) -> list[Candidate]:
        with clock.stage("rerank"):
            passages = [f"{c.heading}\n{c.content}" if c.heading else c.content for c in chunks]
            scores = await self._encoder.score(query, passages)
        ranked = sorted(zip(chunks, scores, strict=True), key=lambda pair: (-pair[1], pair[0].id))
        return [Candidate(chunk.id, score, score) for chunk, score in ranked]


class QueryRewriter:
    SYSTEM = (
        "You rewrite questions into keyword search queries for a full-text index over classic "
        "public-domain books. Keep names, technical terms and numbers. Add close synonyms that "
        "the source text is likely to use. Reply with the query only, on one line."
    )

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def rewrite(self, question: str, clock: StageClock) -> tuple[str, TokenUsage]:
        with clock.stage("rewrite"):
            response = await self._llm.complete(
                LLMRequest(
                    system=self.SYSTEM,
                    prompt=f"Question: {question}",
                    inputs=RewriteInputs(question=question),
                    max_tokens=1024,
                )
            )
        rewritten = " ".join(response.text.split()) or question
        return rewritten, response.usage


class IndexGuard:
    """Refuses queries when the index was embedded by a different model than the active embedder.

    A positive check is cached briefly so the hot path does not scan the chunk table, while a
    re-ingest from another process (the CLI) is still noticed within the TTL.
    """

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, ttl_seconds: float = 60.0
    ) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._ttl = ttl_seconds
        self._verified_at: float | None = None

    def reset(self) -> None:
        self._verified_at = None

    async def check(self) -> None:
        now = time.monotonic()
        if self._verified_at is not None and now - self._verified_at < self._ttl:
            return
        async with self._sessions() as session:
            models = await ChunkRepository(session).embedding_models()
        if models and models != [self._embedder.model_name]:
            self._verified_at = None
            raise IndexMismatchError(
                f"Index was built with {', '.join(models)} but the active embedder is "
                f"{self._embedder.model_name}. Re-run `rlab ingest --force` or change RLAB_EMBEDDER."
            )
        self._verified_at = now if models else None
