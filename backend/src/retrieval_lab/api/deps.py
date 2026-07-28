from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_lab.container import Container
from retrieval_lab.errors import TooManyRunsError, UnauthorizedError
from retrieval_lab.log import get_logger
from retrieval_lab.settings import Settings

log = get_logger(__name__)


class RunScheduler:
    """Keeps references to in-flight eval runs so they are not garbage collected mid-run."""

    def __init__(self, container: Container, max_active: int) -> None:
        self._container = container
        self._max_active = max_active
        self._tasks: dict[uuid.UUID, asyncio.Task[object]] = {}
        self._reserved = 0

    @contextmanager
    def reserve(self) -> Iterator[None]:
        """Hold a slot while a run is being created, so concurrent requests cannot overshoot the cap.

        Creating the run awaits the database, and a plain capacity check before that await would
        let every request that arrives in the meantime through.
        """
        in_use = len(self._tasks) + self._reserved
        if in_use >= self._max_active:
            raise TooManyRunsError(f"{in_use} eval runs are already in progress; wait for one to finish")
        self._reserved += 1
        try:
            yield
        finally:
            self._reserved -= 1

    def submit(self, run_id: uuid.UUID) -> None:
        task: asyncio.Task[object] = asyncio.create_task(self._container.runner.execute(run_id))
        self._tasks[run_id] = task
        task.add_done_callback(lambda t: self._finished(run_id, t))

    def _finished(self, run_id: uuid.UUID, task: asyncio.Task[object]) -> None:
        self._tasks.pop(run_id, None)
        if not task.cancelled() and task.exception() is not None:
            log.warning("background_run_failed", run_id=str(run_id))

    @property
    def active(self) -> int:
        return len(self._tasks)

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_token(request: Request) -> None:
    settings: Settings = request.app.state.settings
    token = settings.api_token
    if token is None or request.method in _SAFE_METHODS:
        return
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        supplied.encode(), token.get_secret_value().encode()
    ):
        raise UnauthorizedError("This endpoint needs a valid bearer token (RLAB_API_TOKEN)")


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_scheduler(request: Request) -> RunScheduler:
    scheduler: RunScheduler = request.app.state.scheduler
    return scheduler


async def get_session(container: Annotated[Container, Depends(get_container)]) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


class Pagination:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SchedulerDep = Annotated[RunScheduler, Depends(get_scheduler)]
PaginationDep = Annotated[Pagination, Depends()]
