from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from retrieval_lab.api.deps import ContainerDep, SessionDep
from retrieval_lab.api.schemas import ChunkOut, CorpusOut, DocumentOut, HealthOut
from retrieval_lab.db.models import Chunk
from retrieval_lab.errors import NotFoundError
from retrieval_lab.repositories.chunks import ChunkRepository
from retrieval_lab.repositories.documents import DocumentRepository

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(container: ContainerDep, session: SessionDep) -> HealthOut:
    database = True
    chunk_count = 0
    try:
        await session.execute(text("SELECT 1"))
        chunk_count = int(await session.scalar(select(func.count()).select_from(Chunk)) or 0)
    except Exception:
        database = False
    return HealthOut(
        status="ok" if database else "degraded",
        database=database,
        offline=container.settings.offline,
        llm_model=container.llm.model,
        judge_model=container.judge.model,
        embedding_model=container.embedder.model_name,
        reranker_model=container.cross_encoder.model_name,
        chunk_count=chunk_count,
    )


@router.get("/corpus")
async def corpus(container: ContainerDep, session: SessionDep) -> CorpusOut:
    documents = await DocumentRepository(session).summaries()
    return CorpusOut(
        documents=[
            DocumentOut(
                slug=d.slug,
                title=d.title,
                author=d.author,
                source_url=d.source_url,
                characters=d.characters,
                chunk_count=d.chunk_count,
            )
            for d in documents
        ],
        chunk_count=sum(d.chunk_count for d in documents),
        embedding_model=container.embedder.model_name,
    )


@router.get("/chunks/{chunk_id}")
async def chunk(chunk_id: str, session: SessionDep) -> ChunkOut:
    views = await ChunkRepository(session).fetch([chunk_id])
    view = views.get(chunk_id)
    if view is None:
        raise NotFoundError(f"Chunk {chunk_id} not found")
    return ChunkOut(
        id=view.id,
        document_slug=view.document_slug,
        document_title=view.document_title,
        heading=view.heading,
        content=view.content,
        char_start=view.char_start,
        char_end=view.char_end,
        token_count=view.token_count,
    )
