from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from retrieval_lab.db.models import (
    Baseline,
    EvalResult,
    EvalRun,
    GoldenQuestion,
    JudgeCalibration,
    PipelineConfigRow,
    RunStatus,
)
from retrieval_lab.errors import NotFoundError

ResultSort = Literal["ndcg_asc", "ndcg_desc", "question"]


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        config_id: uuid.UUID,
        mode: str,
        trigger: str,
        label: str | None,
        k: int,
        question_count: int,
        llm_model: str,
        judge_model: str,
    ) -> EvalRun:
        run = EvalRun(
            config_id=config_id,
            status=RunStatus.QUEUED,
            mode=mode,
            trigger=trigger,
            label=label,
            k=k,
            question_count=question_count,
            completed_count=0,
            llm_model=llm_model,
            judge_model=judge_model,
            summary={},
        )
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run, attribute_names=["config"])
        return run

    async def get(self, run_id: uuid.UUID) -> EvalRun:
        run = await self._session.get(EvalRun, run_id)
        if run is None:
            raise NotFoundError(f"Eval run {run_id} not found")
        return run

    async def get_many(self, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, EvalRun]:
        if not run_ids:
            return {}
        rows = await self._session.execute(select(EvalRun).where(EvalRun.id.in_(run_ids)))
        return {run.id: run for run in rows.unique().scalars()}

    async def mark_running(self, run_id: uuid.UUID) -> None:
        await self._session.execute(
            update(EvalRun)
            .where(EvalRun.id == run_id)
            .values(status=RunStatus.RUNNING, started_at=datetime.now(UTC))
        )

    async def add_result(
        self, run_id: uuid.UUID, question_id: uuid.UUID, ndcg: float | None, payload: dict[str, Any]
    ) -> None:
        # xmax is 0 only on a freshly inserted row, so a re-scored question is not counted twice.
        inserted = await self._session.scalar(
            insert(EvalResult)
            .values(
                id=uuid.uuid4(),
                run_id=run_id,
                question_id=question_id,
                ndcg=ndcg,
                payload=payload,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["run_id", "question_id"], set_={"ndcg": ndcg, "payload": payload}
            )
            .returning(literal_column("xmax = 0"))
        )
        if inserted:
            await self._session.execute(
                update(EvalRun)
                .where(EvalRun.id == run_id)
                .values(completed_count=EvalRun.completed_count + 1)
            )

    async def finish(self, run_id: uuid.UUID, summary: dict[str, Any]) -> None:
        await self._session.execute(
            update(EvalRun)
            .where(EvalRun.id == run_id)
            .values(status=RunStatus.COMPLETED, summary=summary, finished_at=datetime.now(UTC))
        )

    async def fail(self, run_id: uuid.UUID, error: str) -> None:
        await self._session.execute(
            update(EvalRun)
            .where(EvalRun.id == run_id)
            .values(status=RunStatus.FAILED, error=error[:2000], finished_at=datetime.now(UTC))
        )

    async def fail_interrupted(self, *, trigger: str) -> int:
        """Fail runs a previous process left queued or running; nothing will ever finish them."""
        result = await self._session.execute(
            update(EvalRun)
            .where(
                EvalRun.trigger == trigger,
                EvalRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
            )
            .values(
                status=RunStatus.FAILED,
                error="Interrupted: the API restarted before the run finished",
                finished_at=datetime.now(UTC),
            )
            .returning(EvalRun.id)
        )
        return len(result.all())

    async def page(
        self,
        *,
        config_name: str | None,
        status: RunStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[EvalRun], int]:
        stmt = select(EvalRun).join(PipelineConfigRow, PipelineConfigRow.id == EvalRun.config_id)
        if config_name:
            stmt = stmt.where(PipelineConfigRow.name == config_name)
        if status is not None:
            stmt = stmt.where(EvalRun.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(EvalRun.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.unique().scalars()), int(total or 0)

    async def latest_completed_per_config(self) -> list[EvalRun]:
        ranked = (
            select(
                EvalRun.id,
                func.row_number()
                .over(partition_by=PipelineConfigRow.name, order_by=EvalRun.finished_at.desc())
                .label("position"),
            )
            .join(PipelineConfigRow, PipelineConfigRow.id == EvalRun.config_id)
            .where(EvalRun.status == RunStatus.COMPLETED, EvalRun.mode == "full")
            .subquery()
        )
        latest = aliased(EvalRun)
        rows = await self._session.execute(
            select(latest).join(ranked, ranked.c.id == latest.id).where(ranked.c.position == 1)
        )
        return list(rows.unique().scalars())

    async def history(self, config_name: str, limit: int = 20) -> list[EvalRun]:
        rows = await self._session.execute(
            select(EvalRun)
            .join(PipelineConfigRow, PipelineConfigRow.id == EvalRun.config_id)
            .where(PipelineConfigRow.name == config_name, EvalRun.status == RunStatus.COMPLETED)
            .order_by(EvalRun.finished_at.desc())
            .limit(limit)
        )
        return list(rows.unique().scalars())

    async def results_page(
        self, run_id: uuid.UUID, *, sort: ResultSort, offset: int, limit: int
    ) -> tuple[list[EvalResult], int]:
        total = await self._session.scalar(
            select(func.count()).select_from(EvalResult).where(EvalResult.run_id == run_id)
        )
        golden = aliased(GoldenQuestion)
        order = {
            "ndcg_asc": (EvalResult.ndcg.asc().nulls_last(), EvalResult.id),
            "ndcg_desc": (EvalResult.ndcg.desc().nulls_last(), EvalResult.id),
            "question": (golden.external_id.asc().nulls_last(), golden.created_at, EvalResult.id),
        }[sort]
        rows = await self._session.execute(
            select(EvalResult)
            .join(golden, golden.id == EvalResult.question_id)
            .where(EvalResult.run_id == run_id)
            .order_by(*order)
            .offset(offset)
            .limit(limit)
        )
        return list(rows.unique().scalars()), int(total or 0)

    async def all_results(self, run_id: uuid.UUID) -> list[EvalResult]:
        rows = await self._session.execute(select(EvalResult).where(EvalResult.run_id == run_id))
        return list(rows.unique().scalars())

    async def result(self, run_id: uuid.UUID, question_id: uuid.UUID) -> EvalResult:
        rows = await self._session.execute(
            select(EvalResult).where(EvalResult.run_id == run_id, EvalResult.question_id == question_id)
        )
        found = rows.unique().scalar_one_or_none()
        if found is None:
            raise NotFoundError(f"No result for question {question_id} in run {run_id}")
        return found

    async def set_baseline(self, config_name: str, run_id: uuid.UUID) -> None:
        await self._session.execute(
            insert(Baseline)
            .values(config_name=config_name, run_id=run_id, promoted_at=datetime.now(UTC))
            .on_conflict_do_update(
                index_elements=["config_name"], set_={"run_id": run_id, "promoted_at": datetime.now(UTC)}
            )
        )

    async def baselines(self) -> dict[str, uuid.UUID]:
        rows = await self._session.execute(select(Baseline.config_name, Baseline.run_id))
        return dict(rows.all())

    async def baseline_for(self, config_name: str) -> EvalRun | None:
        run_id = await self._session.scalar(
            select(Baseline.run_id).where(Baseline.config_name == config_name)
        )
        return None if run_id is None else await self.get(run_id)


class CalibrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, judge_model: str, sample_size: int, kappa: float, agreement: float, payload: dict[str, Any]
    ) -> JudgeCalibration:
        row = JudgeCalibration(
            judge_model=judge_model,
            sample_size=sample_size,
            kappa=kappa,
            agreement=agreement,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest(self) -> JudgeCalibration | None:
        rows = await self._session.execute(
            select(JudgeCalibration).order_by(JudgeCalibration.created_at.desc()).limit(1)
        )
        return rows.scalar_one_or_none()
