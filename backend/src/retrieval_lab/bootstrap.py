"""Loading checked-in data (pipeline configs, golden set) into the database."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from retrieval_lab.container import Container
from retrieval_lab.db.models import GoldenOrigin, GoldenStatus
from retrieval_lab.db.session import transaction
from retrieval_lab.repositories.configs import ConfigRepository
from retrieval_lab.repositories.golden import GoldenDraft, GoldenRepository
from retrieval_lab.retrieval.config import PipelineConfig


class SeedQuestion(BaseModel):
    id: str
    question: str
    document: str | None
    evidence: str | None
    answer: str | None
    answerable: bool


class ConfigSyncResult(BaseModel):
    name: str
    version: int
    spec_hash: str
    created: bool


def load_pipeline_files(directory: Path) -> list[PipelineConfig]:
    return [
        PipelineConfig.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


async def sync_configs(container: Container, configs: list[PipelineConfig]) -> list[ConfigSyncResult]:
    results: list[ConfigSyncResult] = []
    async with transaction(container.sessions) as session:
        repo = ConfigRepository(session)
        for config in configs:
            row, created = await repo.register(config)
            results.append(
                ConfigSyncResult(name=row.name, version=row.version, spec_hash=row.spec_hash, created=created)
            )
    return results


def load_seed_questions(path: Path) -> list[SeedQuestion]:
    return [
        SeedQuestion.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def load_golden_seed(container: Container, path: Path) -> tuple[int, int]:
    drafts = [
        GoldenDraft(
            question=q.question,
            document_slug=q.document,
            evidence=q.evidence,
            reference_answer=q.answer,
            answerable=q.answerable,
            status=GoldenStatus.ACCEPTED,
            origin=GoldenOrigin.SEED,
            external_id=q.id,
        )
        for q in load_seed_questions(path)
    ]
    async with transaction(container.sessions) as session:
        return await GoldenRepository(session).upsert_external(drafts)
