from __future__ import annotations

import asyncio

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_lab.db.models import GoldenOrigin, GoldenQuestion, GoldenStatus
from retrieval_lab.db.session import transaction
from retrieval_lab.evals.evidence import locate
from retrieval_lab.llm.base import LLMProvider, LLMRequest, SynthesisInputs, SynthesizedQuestion, TokenUsage
from retrieval_lab.log import get_logger
from retrieval_lab.repositories.chunks import ChunkRepository, ChunkView
from retrieval_lab.repositories.documents import DocumentRepository
from retrieval_lab.repositories.golden import GoldenDraft, GoldenRepository

log = get_logger(__name__)

SYSTEM = """You write evaluation questions for a retrieval system over public-domain books.

Given one passage, write a single question a curious reader might ask that this passage answers. \
The question must make sense without seeing the passage, so name the subject instead of saying \
"the passage" or "the author". Copy the shortest verbatim sentence from the passage that contains \
the answer into `evidence`, and give a one-sentence answer."""

SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "evidence": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["question", "evidence", "answer"],
    "additionalProperties": False,
}


class SynthesisReport(BaseModel):
    created: int
    skipped: int
    usage: TokenUsage
    question_ids: list[str]


class QuestionSynthesizer:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], llm: LLMProvider) -> None:
        self._sessions = sessions
        self._llm = llm

    async def _draft(self, chunk: ChunkView) -> tuple[SynthesizedQuestion | None, TokenUsage]:
        response = await self._llm.complete(
            LLMRequest(
                system=SYSTEM,
                prompt=(
                    f"Book: {chunk.document_title}\nSection: {chunk.heading}\n\n"
                    f"<passage>\n{chunk.content}\n</passage>"
                ),
                inputs=SynthesisInputs(
                    title=chunk.document_title, heading=chunk.heading, passage=chunk.content
                ),
                max_tokens=1024,
                json_schema=SCHEMA,
            )
        )
        try:
            return SynthesizedQuestion.model_validate_json(response.text), response.usage
        except ValidationError:
            log.warning("synthesis_unparseable", chunk_id=chunk.id)
            return None, response.usage

    async def generate(
        self, count: int, *, document_slug: str | None = None, seed: float | None = None
    ) -> SynthesisReport:
        async with self._sessions() as session:
            chunks = await ChunkRepository(session).sample(count, document_slug, seed=seed)
            known = await GoldenRepository(session).existing_questions()
            contents = await DocumentRepository(session).contents(sorted({c.document_slug for c in chunks}))

        drafts = await asyncio.gather(*(self._draft(chunk) for chunk in chunks))
        usage = TokenUsage()
        created: list[GoldenQuestion] = []
        skipped = 0
        async with transaction(self._sessions) as session:
            repo = GoldenRepository(session)
            for chunk, (draft, used) in zip(chunks, drafts, strict=True):
                usage = usage + used
                if draft is None or draft.question.lower() in known:
                    skipped += 1
                    continue
                # Fall back to the whole chunk when the model paraphrased instead of quoting.
                evidence = (
                    draft.evidence
                    if locate(contents.get(chunk.document_slug, ""), draft.evidence)
                    else chunk.content
                )
                known.add(draft.question.lower())
                created.append(
                    await repo.add(
                        GoldenDraft(
                            question=draft.question,
                            document_slug=chunk.document_slug,
                            evidence=evidence,
                            reference_answer=draft.answer,
                            answerable=True,
                            status=GoldenStatus.PROPOSED,
                            origin=GoldenOrigin.SYNTHETIC,
                            source_chunk_id=chunk.id,
                        )
                    )
                )
        return SynthesisReport(
            created=len(created), skipped=skipped, usage=usage, question_ids=[str(q.id) for q in created]
        )
