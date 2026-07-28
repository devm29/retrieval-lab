from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_lab.db.models import Chunk, Document


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    slug: str
    title: str
    author: str | None
    source_url: str | None
    characters: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class NewChunk:
    id: str
    ordinal: int
    heading: str
    content: str
    char_start: int
    char_end: int
    token_count: int
    embedding: list[float]
    embedding_model: str


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slug(self, slug: str) -> Document | None:
        result = await self._session.execute(select(Document).where(Document.slug == slug))
        return result.scalar_one_or_none()

    async def contents(self, slugs: Sequence[str]) -> dict[str, str]:
        if not slugs:
            return {}
        rows = await self._session.execute(
            select(Document.slug, Document.content).where(Document.slug.in_(list(slugs)))
        )
        return dict(rows.all())

    async def upsert(
        self,
        *,
        slug: str,
        title: str,
        author: str | None,
        source_url: str | None,
        content: str,
        content_hash: str,
        chunking: dict[str, Any],
    ) -> Document:
        document = await self.get_by_slug(slug)
        if document is None:
            document = Document(slug=slug)
            self._session.add(document)
        document.title = title
        document.author = author
        document.source_url = source_url
        document.content = content
        document.content_hash = content_hash
        document.chunking = chunking
        await self._session.flush()
        return document

    async def replace_chunks(self, document: Document, chunks: Sequence[NewChunk]) -> None:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        self._session.add_all(
            Chunk(
                id=c.id,
                document_id=document.id,
                ordinal=c.ordinal,
                heading=c.heading,
                content=c.content,
                char_start=c.char_start,
                char_end=c.char_end,
                token_count=c.token_count,
                embedding=c.embedding,
                embedding_model=c.embedding_model,
            )
            for c in chunks
        )
        await self._session.flush()

    async def delete_missing(self, keep_slugs: Sequence[str]) -> int:
        result = await self._session.execute(
            delete(Document).where(Document.slug.not_in(list(keep_slugs))).returning(Document.id)
        )
        return len(result.all())

    async def summaries(self) -> list[DocumentSummary]:
        chunk_counts = (
            select(Chunk.document_id, func.count(Chunk.id).label("n")).group_by(Chunk.document_id).subquery()
        )
        rows = await self._session.execute(
            select(
                Document.slug,
                Document.title,
                Document.author,
                Document.source_url,
                func.length(Document.content),
                func.coalesce(chunk_counts.c.n, 0),
            )
            .outerjoin(chunk_counts, chunk_counts.c.document_id == Document.id)
            .order_by(Document.title)
        )
        return [DocumentSummary(*row) for row in rows]
