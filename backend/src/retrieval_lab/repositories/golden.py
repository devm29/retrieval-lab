from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_lab.db.models import GoldenOrigin, GoldenQuestion, GoldenStatus
from retrieval_lab.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class GoldenDraft:
    question: str
    document_slug: str | None
    evidence: str | None
    reference_answer: str | None
    answerable: bool
    status: GoldenStatus
    origin: GoldenOrigin
    external_id: str | None = None
    source_chunk_id: str | None = None


class GoldenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, question_id: uuid.UUID) -> GoldenQuestion:
        row = await self._session.get(GoldenQuestion, question_id)
        if row is None:
            raise NotFoundError(f"Golden question {question_id} not found")
        return row

    async def accepted(self) -> list[GoldenQuestion]:
        result = await self._session.execute(
            select(GoldenQuestion)
            .where(GoldenQuestion.status == GoldenStatus.ACCEPTED)
            .order_by(GoldenQuestion.external_id.nulls_last(), GoldenQuestion.created_at)
        )
        return list(result.scalars())

    async def page(
        self, *, status: GoldenStatus | None, origin: GoldenOrigin | None, offset: int, limit: int
    ) -> tuple[list[GoldenQuestion], int]:
        stmt = select(GoldenQuestion)
        if status is not None:
            stmt = stmt.where(GoldenQuestion.status == status)
        if origin is not None:
            stmt = stmt.where(GoldenQuestion.origin == origin)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(GoldenQuestion.created_at.desc(), GoldenQuestion.id).offset(offset).limit(limit)
        )
        return list(rows.scalars()), int(total or 0)

    async def counts(self) -> dict[str, int]:
        rows = await self._session.execute(
            select(GoldenQuestion.status, func.count()).group_by(GoldenQuestion.status)
        )
        counts = {status.value: 0 for status in GoldenStatus}
        counts.update({status.value: int(n) for status, n in rows})
        return counts

    async def existing_questions(self) -> set[str]:
        rows = await self._session.execute(select(func.lower(GoldenQuestion.question)))
        return set(rows.scalars())

    async def add(self, draft: GoldenDraft) -> GoldenQuestion:
        row = GoldenQuestion(
            external_id=draft.external_id,
            question=draft.question,
            document_slug=draft.document_slug,
            evidence=draft.evidence,
            reference_answer=draft.reference_answer,
            answerable=draft.answerable,
            status=draft.status,
            origin=draft.origin,
            source_chunk_id=draft.source_chunk_id,
            reviewed_at=datetime.now(UTC) if draft.status is not GoldenStatus.PROPOSED else None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def upsert_external(self, drafts: Sequence[GoldenDraft]) -> tuple[int, int]:
        ids = [d.external_id for d in drafts if d.external_id]
        result = await self._session.execute(
            select(GoldenQuestion).where(GoldenQuestion.external_id.in_(ids))
        )
        existing = {row.external_id: row for row in result.scalars()}
        created = updated = 0
        for draft in drafts:
            row = existing.get(draft.external_id)
            if row is None:
                await self.add(draft)
                created += 1
                continue
            row.question = draft.question
            row.document_slug = draft.document_slug
            row.evidence = draft.evidence
            row.reference_answer = draft.reference_answer
            row.answerable = draft.answerable
            updated += 1
        await self._session.flush()
        return created, updated
