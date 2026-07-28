from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_lab.db.session import transaction
from retrieval_lab.ingest.chunker import ChunkingParams, chunk_markdown
from retrieval_lab.ingest.embedder import Embedder
from retrieval_lab.ingest.loader import SourceDocument
from retrieval_lab.log import get_logger
from retrieval_lab.repositories.chunks import ChunkRepository
from retrieval_lab.repositories.documents import DocumentRepository, NewChunk

log = get_logger(__name__)


class DocumentIngestResult(BaseModel):
    slug: str
    chunks: int
    skipped: bool


class IngestReport(BaseModel):
    documents: list[DocumentIngestResult]
    removed: int
    embedding_model: str
    seconds: float

    @property
    def chunk_total(self) -> int:
        return sum(d.chunks for d in self.documents)


def embedding_text(title: str, heading: str, content: str) -> str:
    # Prefixing the title and section path gives short chunks enough context to embed well.
    header = f"{title} — {heading}" if heading else title
    return f"{header}\n\n{content}"


class IngestService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        params: ChunkingParams,
        on_index_changed: Callable[[], None] | None = None,
    ) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._params = params
        self._on_index_changed = on_index_changed

    def _fingerprint(self) -> dict[str, object]:
        return {**self._params.model_dump(), "embedding_model": self._embedder.model_name}

    async def ingest(
        self, documents: Sequence[SourceDocument], *, force: bool = False, prune: bool = True
    ) -> IngestReport:
        started = time.perf_counter()
        results: list[DocumentIngestResult] = []
        fingerprint = self._fingerprint()
        for source in documents:
            async with self._sessions() as session:
                existing = await DocumentRepository(session).get_by_slug(source.slug)
                unchanged = (
                    existing is not None
                    and existing.content_hash == source.content_hash
                    and existing.chunking == fingerprint
                )
            if unchanged and not force:
                results.append(DocumentIngestResult(slug=source.slug, chunks=0, skipped=True))
                continue

            # Embed before opening the write transaction so no connection idles in it.
            drafts = chunk_markdown(source.content, self._params)
            vectors = await self._embedder.embed_documents(
                [embedding_text(source.title, d.heading, d.content) for d in drafts]
            )
            async with transaction(self._sessions) as session:
                repo = DocumentRepository(session)
                document = await repo.upsert(
                    slug=source.slug,
                    title=source.title,
                    author=source.author,
                    source_url=source.source_url,
                    content=source.content,
                    content_hash=source.content_hash,
                    chunking=fingerprint,
                )
                await repo.replace_chunks(
                    document,
                    [
                        NewChunk(
                            id=f"{source.slug}:{d.ordinal:04d}",
                            ordinal=d.ordinal,
                            heading=d.heading,
                            content=d.content,
                            char_start=d.char_start,
                            char_end=d.char_end,
                            token_count=d.token_count,
                            embedding=vector,
                            embedding_model=self._embedder.model_name,
                        )
                        for d, vector in zip(drafts, vectors, strict=True)
                    ],
                )
            log.info("document_ingested", slug=source.slug, chunks=len(drafts))
            results.append(DocumentIngestResult(slug=source.slug, chunks=len(drafts), skipped=False))

        removed = 0
        async with transaction(self._sessions) as session:
            if prune:
                removed = await DocumentRepository(session).delete_missing([d.slug for d in documents])
            changed = bool(removed) or any(not r.skipped for r in results)
            if changed:
                await ChunkRepository(session).refresh_bm25_stats()
        if changed and self._on_index_changed is not None:
            self._on_index_changed()
        return IngestReport(
            documents=results,
            removed=removed,
            embedding_model=self._embedder.model_name,
            seconds=round(time.perf_counter() - started, 2),
        )
