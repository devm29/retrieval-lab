from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from retrieval_lab.api.deps import ContainerDep, PaginationDep, SessionDep
from retrieval_lab.api.mappers import golden_out
from retrieval_lab.api.schemas import (
    GoldenCreate,
    GoldenOut,
    GoldenPage,
    GoldenUpdate,
    SynthesizeIn,
    SynthesizeOut,
)
from retrieval_lab.db.models import GoldenOrigin, GoldenStatus
from retrieval_lab.db.session import transaction
from retrieval_lab.errors import ValidationFailedError
from retrieval_lab.evals.evidence import locate
from retrieval_lab.repositories.documents import DocumentRepository
from retrieval_lab.repositories.golden import GoldenDraft, GoldenRepository

router = APIRouter(prefix="/golden", tags=["golden"])


async def _check_evidence(
    documents: DocumentRepository, answerable: bool, slug: str | None, evidence: str | None
) -> None:
    if not answerable:
        return
    if not slug or not evidence:
        raise ValidationFailedError("Answerable questions need a document and an evidence quote")
    contents = await documents.contents([slug])
    if slug not in contents:
        raise ValidationFailedError(f"Unknown document '{slug}'")
    if locate(contents[slug], evidence) is None:
        raise ValidationFailedError("The evidence quote was not found verbatim in the document")


@router.get("")
async def list_golden(
    session: SessionDep,
    pagination: PaginationDep,
    status_filter: Annotated[GoldenStatus | None, Query(alias="status")] = None,
    origin: GoldenOrigin | None = None,
) -> GoldenPage:
    repo = GoldenRepository(session)
    rows, total = await repo.page(
        status=status_filter, origin=origin, offset=pagination.offset, limit=pagination.page_size
    )
    return GoldenPage(
        items=[golden_out(r) for r in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        counts=await repo.counts(),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_golden(body: GoldenCreate, container: ContainerDep) -> GoldenOut:
    async with transaction(container.sessions) as session:
        await _check_evidence(DocumentRepository(session), body.answerable, body.document_slug, body.evidence)
        row = await GoldenRepository(session).add(
            GoldenDraft(
                question=body.question.strip(),
                document_slug=body.document_slug if body.answerable else None,
                evidence=body.evidence if body.answerable else None,
                reference_answer=body.reference_answer,
                answerable=body.answerable,
                status=GoldenStatus.ACCEPTED,
                origin=GoldenOrigin.MANUAL,
            )
        )
    return golden_out(row)


@router.patch("/{question_id}")
async def update_golden(question_id: uuid.UUID, body: GoldenUpdate, container: ContainerDep) -> GoldenOut:
    changes = body.model_dump(exclude_unset=True)
    if "question" in changes:
        changes["question"] = changes["question"].strip()
    async with transaction(container.sessions) as session:
        row = await GoldenRepository(session).get(question_id)
        for field, value in changes.items():
            setattr(row, field, value)
        if not row.answerable:
            # Same shape as a question created unanswerable: no evidence to locate or hash.
            row.document_slug = None
            row.evidence = None
        if {"evidence", "document_slug", "answerable"} & changes.keys() or (
            changes.get("status") is GoldenStatus.ACCEPTED
        ):
            await _check_evidence(
                DocumentRepository(session), row.answerable, row.document_slug, row.evidence
            )
        if "status" in changes:
            row.reviewed_at = datetime.now(UTC)
    return golden_out(row)


@router.post("/synthesize", status_code=status.HTTP_201_CREATED)
async def synthesize(body: SynthesizeIn, container: ContainerDep) -> SynthesizeOut:
    report = await container.synthesizer.generate(body.count, document_slug=body.document_slug)
    async with container.sessions() as session:
        repo = GoldenRepository(session)
        rows = [await repo.get(uuid.UUID(qid)) for qid in report.question_ids]
    return SynthesizeOut(
        created=report.created,
        skipped=report.skipped,
        cost_usd=report.usage.cost_usd,
        questions=[golden_out(r) for r in rows],
    )
