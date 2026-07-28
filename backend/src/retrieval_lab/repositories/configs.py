from __future__ import annotations

import uuid

from pydantic import TypeAdapter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_lab.db.models import PipelineConfigRow
from retrieval_lab.errors import NotFoundError, ValidationFailedError
from retrieval_lab.retrieval.config import AnyPipeline, PipelineConfig, PipelineSpec

_SPEC_ADAPTER: TypeAdapter[AnyPipeline] = TypeAdapter(PipelineSpec)


def spec_of(row: PipelineConfigRow) -> AnyPipeline:
    return _SPEC_ADAPTER.validate_python(row.spec)


class ConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, config: PipelineConfig) -> tuple[PipelineConfigRow, bool]:
        """Return the row for this exact spec, creating the next version if it is new.

        Must run inside a transaction: the advisory lock serialises concurrent registrations of
        one name so they cannot both claim max(version) + 1.
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": f"pipeline_config:{config.name}"}
        )
        digest = config.spec_hash
        existing = await self._session.execute(
            select(PipelineConfigRow).where(
                PipelineConfigRow.name == config.name, PipelineConfigRow.spec_hash == digest
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            if config.description and row.description != config.description:
                row.description = config.description
            return row, False
        latest = await self._session.execute(
            select(func.max(PipelineConfigRow.version)).where(PipelineConfigRow.name == config.name)
        )
        row = PipelineConfigRow(
            name=config.name,
            version=(latest.scalar_one_or_none() or 0) + 1,
            spec_hash=digest,
            kind=config.spec.kind,
            description=config.description,
            spec=config.spec.model_dump(mode="json"),
        )
        self._session.add(row)
        await self._session.flush()
        return row, True

    async def get(self, config_id: uuid.UUID) -> PipelineConfigRow:
        row = await self._session.get(PipelineConfigRow, config_id)
        if row is None:
            raise NotFoundError(f"Pipeline config {config_id} not found")
        return row

    async def latest_by_name(self, name: str) -> PipelineConfigRow:
        result = await self._session.execute(
            select(PipelineConfigRow)
            .where(PipelineConfigRow.name == name)
            .order_by(PipelineConfigRow.version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"No pipeline config named '{name}'")
        return row

    async def is_latest(self, row: PipelineConfigRow) -> bool:
        newest = await self._session.scalar(
            select(func.max(PipelineConfigRow.version)).where(PipelineConfigRow.name == row.name)
        )
        return newest == row.version

    async def resolve(self, ref: str) -> PipelineConfigRow:
        """Accept a UUID, a name (latest version) or name@version."""
        try:
            return await self.get(uuid.UUID(ref))
        except ValueError:
            pass
        name, _, version = ref.partition("@")
        if not version:
            return await self.latest_by_name(name)
        if not (version.isascii() and version.isdigit()) or len(version) > 9:
            raise ValidationFailedError(f"'{ref}' is not a valid config reference; use name@<version number>")
        result = await self._session.execute(
            select(PipelineConfigRow).where(
                PipelineConfigRow.name == name, PipelineConfigRow.version == int(version)
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"No pipeline config '{ref}'")
        return row

    async def list_all(self) -> list[PipelineConfigRow]:
        result = await self._session.execute(
            select(PipelineConfigRow).order_by(PipelineConfigRow.name, PipelineConfigRow.version.desc())
        )
        return list(result.scalars())
