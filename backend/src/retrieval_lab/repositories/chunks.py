from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Float, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_lab.db.models import Chunk, Document

BM25_K1 = 1.2
BM25_B = 0.75

# Okapi BM25 over the stored tsvectors: term frequency comes from lexeme positions, IDF from
# lexeme_stats, document length and its corpus average from term_count and corpus_stats, and
# the GIN index narrows candidates to chunks matching any term.
_BM25_SQL = text(
    """
    WITH terms AS (
        SELECT DISTINCT lexeme FROM unnest(to_tsvector('english', :query))
    ),
    q AS (
        SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS query FROM terms
    ),
    stats AS (
        SELECT greatest(avg_term_count, 1.0) AS avgdl,
               (SELECT sum(idf) * (:k1 + 1) FROM lexeme_stats JOIN terms USING (lexeme)) AS ceiling
        FROM corpus_stats
    ),
    candidates AS (
        SELECT c.id, c.tsv, coalesce(c.term_count, 0) AS doc_len FROM chunks c, q
        WHERE q.query IS NOT NULL AND c.tsv @@ q.query
    )
    SELECT cand.id,
           sum(
               ls.idf * (cardinality(t.positions) * (:k1 + 1))
               / (cardinality(t.positions) + :k1 * (1 - :b + :b * cand.doc_len / stats.avgdl))
           ) AS score,
           max(stats.ceiling) AS ceiling
    FROM candidates cand
    CROSS JOIN LATERAL unnest(cand.tsv) AS t(lexeme, positions, weights)
    JOIN terms ON terms.lexeme = t.lexeme
    JOIN lexeme_stats ls ON ls.lexeme = t.lexeme
    CROSS JOIN stats
    GROUP BY cand.id
    ORDER BY score DESC, cand.id
    LIMIT :k
    """
).columns(score=Float, ceiling=Float)

_REFRESH_STATS_SQL = (
    text("DELETE FROM lexeme_stats"),
    text(
        """
        INSERT INTO lexeme_stats (lexeme, ndoc, idf)
        SELECT word, ndoc, ln(1 + (total.n - ndoc + 0.5) / (ndoc + 0.5))
        FROM ts_stat('SELECT tsv FROM chunks'), (SELECT count(*)::float AS n FROM chunks) AS total
        """
    ),
    text(
        """
        UPDATE chunks SET term_count = (SELECT coalesce(sum(cardinality(positions)), 0) FROM unnest(tsv))
        WHERE term_count IS NULL
        """
    ),
    text(
        """
        INSERT INTO corpus_stats (id, chunk_count, avg_term_count)
        SELECT 1, count(*), coalesce(avg(term_count), 0) FROM chunks
        ON CONFLICT (id) DO UPDATE
        SET chunk_count = excluded.chunk_count, avg_term_count = excluded.avg_term_count
        """
    ),
)


@dataclass(frozen=True, slots=True)
class ChunkView:
    id: str
    document_slug: str
    document_title: str
    heading: str
    content: str
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True, slots=True)
class ChunkSpan:
    id: str
    char_start: int
    char_end: int


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bm25(self, query: str, k: int) -> list[tuple[str, float, float]]:
        """Return (chunk id, BM25 score, score as a share of the best score this query could get)."""
        rows = await self._session.execute(_BM25_SQL, {"query": query, "k": k, "k1": BM25_K1, "b": BM25_B})
        return [(row.id, float(row.score), float(row.score) / (row.ceiling or 1.0)) for row in rows]

    async def refresh_bm25_stats(self) -> None:
        for statement in _REFRESH_STATS_SQL:
            await self._session.execute(statement)

    async def dense(self, vector: Sequence[float], k: int, ef_search: int) -> list[tuple[str, float]]:
        # SET LOCAL cannot take bind parameters; ef_search is a validated int.
        await self._session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
        distance = Chunk.embedding.cosine_distance(list(vector))
        rows = await self._session.execute(
            select(Chunk.id, (1 - distance).label("similarity")).order_by(distance).limit(k)
        )
        return [(row.id, float(row.similarity)) for row in rows]

    async def similarities(self, vector: Sequence[float], ids: Sequence[str]) -> dict[str, float]:
        if not ids:
            return {}
        distance = Chunk.embedding.cosine_distance(list(vector))
        rows = await self._session.execute(
            select(Chunk.id, (1 - distance).label("similarity")).where(Chunk.id.in_(list(ids)))
        )
        return {row.id: float(row.similarity) for row in rows}

    async def fetch(self, ids: Sequence[str]) -> dict[str, ChunkView]:
        if not ids:
            return {}
        rows = await self._session.execute(
            select(Chunk, Document.slug, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(list(ids)))
        )
        views: dict[str, ChunkView] = {}
        for chunk, slug, title in rows:
            views[chunk.id] = ChunkView(
                id=chunk.id,
                document_slug=slug,
                document_title=title,
                heading=chunk.heading,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
            )
        return views

    async def spans_for_documents(self, slugs: Sequence[str]) -> dict[str, list[ChunkSpan]]:
        if not slugs:
            return {}
        rows = await self._session.execute(
            select(Document.slug, Chunk.id, Chunk.char_start, Chunk.char_end)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.slug.in_(list(slugs)))
            .order_by(Document.slug, Chunk.ordinal)
        )
        spans: dict[str, list[ChunkSpan]] = {}
        for slug, chunk_id, start, end in rows:
            spans.setdefault(slug, []).append(ChunkSpan(chunk_id, start, end))
        return spans

    async def embedding_models(self) -> list[str]:
        rows = await self._session.execute(select(Chunk.embedding_model).distinct())
        return list(rows.scalars())

    async def sample(
        self, limit: int, document_slug: str | None = None, seed: float | None = None
    ) -> list[ChunkView]:
        if seed is not None:
            await self._session.execute(text("SELECT setseed(:seed)").bindparams(bindparam("seed", seed)))
        stmt = (
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.token_count >= 120)
            .order_by(text("random()"))
            .limit(limit)
        )
        if document_slug:
            stmt = stmt.where(Document.slug == document_slug)
        ids = list((await self._session.execute(stmt)).scalars())
        views = await self.fetch(ids)
        return [views[i] for i in ids if i in views]
