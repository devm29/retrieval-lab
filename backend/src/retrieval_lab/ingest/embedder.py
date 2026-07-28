from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from retrieval_lab.text import content_terms

if TYPE_CHECKING:
    from fastembed import TextEmbedding


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """BGE embeddings via ONNX Runtime; the model is loaded on first use."""

    def __init__(self, model_name: str, dim: int, cache_dir: Path, batch_size: int = 64) -> None:
        self._model_name = model_name
        self._dim = dim
        self._cache_dir = cache_dir
        self._batch_size = batch_size
        self._model: TextEmbedding | None = None
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    async def _load(self) -> TextEmbedding:
        async with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = await asyncio.to_thread(
                    TextEmbedding, self._model_name, cache_dir=str(self._cache_dir)
                )
            return self._model

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        model = await self._load()

        def run() -> list[list[float]]:
            return [v.tolist() for v in model.passage_embed(list(texts), batch_size=self._batch_size)]

        return await asyncio.to_thread(run)

    async def embed_query(self, text: str) -> list[float]:
        model = await self._load()

        def run() -> list[float]:
            vector: list[float] = next(iter(model.query_embed(text))).tolist()
            return vector

        return await asyncio.to_thread(run)


class HashingEmbedder:
    """Signed feature hashing over stemmed unigrams and bigrams.

    No model download, fully deterministic. Useful for unit tests and as a
    lexical-flavoured dense baseline; it does not capture synonyms.
    """

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def model_name(self) -> str:
        return f"hashing-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> list[float]:
        terms = content_terms(text)
        features = terms + [f"{a}_{b}" for a, b in pairwise(terms)]
        vector = [0.0] * self._dim
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self._dim
            vector[bucket] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
