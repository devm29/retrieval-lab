from __future__ import annotations

from retrieval_lab.api.schemas import ConfigOut, GoldenOut, RunOut
from retrieval_lab.db.models import EvalRun, GoldenQuestion, PipelineConfigRow
from retrieval_lab.evals.schemas import RunSummary


def config_out(row: PipelineConfigRow, *, is_latest: bool = False) -> ConfigOut:
    return ConfigOut(
        id=row.id,
        name=row.name,
        version=row.version,
        kind=row.kind,
        spec_hash=row.spec_hash,
        description=row.description,
        spec=row.spec,
        created_at=row.created_at,
        is_latest=is_latest,
    )


def run_out(run: EvalRun, *, is_baseline: bool = False) -> RunOut:
    return RunOut(
        id=run.id,
        config=config_out(run.config),
        status=run.status,
        mode=run.mode,
        trigger=run.trigger,
        label=run.label,
        k=run.k,
        question_count=run.question_count,
        completed_count=run.completed_count,
        llm_model=run.llm_model,
        judge_model=run.judge_model,
        summary=RunSummary.model_validate(run.summary) if run.summary else None,
        error=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        is_baseline=is_baseline,
    )


def golden_out(row: GoldenQuestion) -> GoldenOut:
    return GoldenOut.model_validate(row)
