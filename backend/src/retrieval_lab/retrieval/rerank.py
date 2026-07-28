from __future__ import annotations

import asyncio
import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from retrieval_lab.text import content_terms

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder


class CrossEncoder(Protocol):
    @property
    def model_name(self) -> str: ...

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """Relevance probabilities in [0, 1], one per passage."""
        ...


class FastEmbedCrossEncoder:
    def __init__(self, model_name: str, cache_dir: Path) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextCrossEncoder | None = None
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    async def _load(self) -> TextCrossEncoder:
        async with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                self._model = await asyncio.to_thread(
                    TextCrossEncoder, self._model_name, cache_dir=str(self._cache_dir)
                )
            return self._model

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        model = await self._load()

        def run() -> list[float]:
            return [1.0 / (1.0 + math.exp(-float(logit))) for logit in model.rerank(query, list(passages))]

        return await asyncio.to_thread(run)


class LexicalCrossEncoder:
    """BM25-weighted term overlap computed over the candidate set itself.

    A dependency-free fallback when the ONNX cross-encoder is unavailable.
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b

    @property
    def model_name(self) -> str:
        return "lexical-bm25"

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        query_terms = set(content_terms(query))
        docs = [Counter(content_terms(p)) for p in passages]
        avg_len = sum(sum(d.values()) for d in docs) / len(docs) or 1.0
        df = Counter(term for d in docs for term in d.keys() & query_terms)
        n = len(docs)
        raw: list[float] = []
        for doc in docs:
            length = sum(doc.values())
            total = 0.0
            for term in query_terms:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                total += (
                    idf * tf * (self._k1 + 1) / (tf + self._k1 * (1 - self._b + self._b * length / avg_len))
                )
            raw.append(total)
        return [1 - math.exp(-s / 2) for s in raw]
