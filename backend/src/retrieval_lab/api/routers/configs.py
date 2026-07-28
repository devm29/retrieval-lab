from __future__ import annotations

from fastapi import APIRouter, Response, status

from retrieval_lab.api.deps import ContainerDep, SessionDep
from retrieval_lab.api.mappers import config_out
from retrieval_lab.api.schemas import ConfigCreate, ConfigCreated, ConfigOut, HistoryPoint
from retrieval_lab.db.session import transaction
from retrieval_lab.evals.schemas import RunSummary
from retrieval_lab.repositories.configs import ConfigRepository
from retrieval_lab.repositories.runs import RunRepository
from retrieval_lab.retrieval.config import PipelineConfig

router = APIRouter(prefix="/configs", tags=["configs"])


@router.get("")
async def list_configs(session: SessionDep) -> list[ConfigOut]:
    rows = await ConfigRepository(session).list_all()
    latest: dict[str, int] = {}
    for row in rows:
        latest[row.name] = max(latest.get(row.name, 0), row.version)
    return [config_out(row, is_latest=latest[row.name] == row.version) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_config(body: ConfigCreate, container: ContainerDep, response: Response) -> ConfigCreated:
    config = PipelineConfig(name=body.name, description=body.description, spec=body.spec)
    async with transaction(container.sessions) as session:
        configs = ConfigRepository(session)
        row, created = await configs.register(config)
        # Re-registering an older spec returns that older version, which is not the latest.
        latest = created or await configs.is_latest(row)
    if not created:
        response.status_code = status.HTTP_200_OK
    return ConfigCreated(config=config_out(row, is_latest=latest), created=created)


@router.get("/{ref}")
async def get_config(ref: str, session: SessionDep) -> ConfigOut:
    configs = ConfigRepository(session)
    row = await configs.resolve(ref)
    return config_out(row, is_latest=await configs.is_latest(row))


@router.get("/{name}/history")
async def config_history(name: str, session: SessionDep) -> list[HistoryPoint]:
    runs = await RunRepository(session).history(name, limit=50)
    return [
        HistoryPoint(
            run_id=run.id,
            version=run.config.version,
            finished_at=run.finished_at,
            label=run.label,
            metrics=RunSummary.model_validate(run.summary).metrics,
        )
        for run in reversed(runs)
        if run.summary and run.mode == "full"
    ]
