from __future__ import annotations

from fastapi import APIRouter

from retrieval_lab.api.deps import ContainerDep
from retrieval_lab.api.mappers import config_out
from retrieval_lab.api.schemas import QueryIn, QueryOut
from retrieval_lab.repositories.configs import ConfigRepository, spec_of

router = APIRouter(tags=["query"])


@router.post("/query")
async def query(body: QueryIn, container: ContainerDep) -> QueryOut:
    # The config lookup gets its own short session so no connection sits idle in a
    # transaction through embedding, reranking and the LLM call.
    async with container.sessions() as session:
        configs = ConfigRepository(session)
        row = await configs.resolve(body.config)
        latest = await configs.is_latest(row)
    await container.index_guard.check()
    result = await container.answers.answer(body.question.strip(), container.pipeline(spec_of(row)))
    return QueryOut(
        config=config_out(row, is_latest=latest),
        result=result,
        total_cost_usd=round(result.total_cost_usd, 6),
    )
