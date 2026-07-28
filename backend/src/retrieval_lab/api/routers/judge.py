from __future__ import annotations

from fastapi import APIRouter, status

from retrieval_lab.api.deps import ContainerDep, SessionDep
from retrieval_lab.api.schemas import CalibrationOut
from retrieval_lab.db.session import transaction
from retrieval_lab.errors import NotFoundError
from retrieval_lab.evals.calibration import calibrate, load_items
from retrieval_lab.evals.schemas import CalibrationReport
from retrieval_lab.repositories.runs import CalibrationRepository

router = APIRouter(prefix="/judge", tags=["judge"])


@router.get("/calibration")
async def latest_calibration(session: SessionDep) -> CalibrationOut:
    row = await CalibrationRepository(session).latest()
    if row is None:
        raise NotFoundError("The judge has not been calibrated yet")
    return CalibrationOut(
        id=row.id, created_at=row.created_at, report=CalibrationReport.model_validate(row.payload)
    )


@router.post("/calibration", status_code=status.HTTP_201_CREATED)
async def run_calibration(container: ContainerDep) -> CalibrationOut:
    items = load_items(container.settings.data_dir / "golden" / "judge_calibration.jsonl")
    report = await calibrate(container.judge, items, container.settings.eval_concurrency)
    async with transaction(container.sessions) as session:
        row = await CalibrationRepository(session).add(
            judge_model=report.judge_model,
            sample_size=report.sample_size,
            kappa=report.kappa,
            agreement=report.agreement,
            payload=report.model_dump(mode="json"),
        )
    return CalibrationOut(id=row.id, created_at=row.created_at, report=report)
