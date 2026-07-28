from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn

from retrieval_lab.bootstrap import load_golden_seed, load_pipeline_files, sync_configs
from retrieval_lab.container import Container, build_container
from retrieval_lab.ingest.loader import load_corpus
from retrieval_lab.settings import PROJECT_ROOT, Settings

TEST_DATABASE_URL = os.environ.get(
    "RLAB_TEST_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5502/retrieval_lab_test"
)

pytestmark = pytest.mark.db


async def _reset_schema(url: str) -> None:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""), timeout=3)
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def _migrate(url: str) -> None:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        database_url=PostgresDsn(TEST_DATABASE_URL),
        embedder="hashing",
        reranker="lexical",
        llm_provider="fake",
        eval_concurrency=4,
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
async def container(settings: Settings) -> AsyncIterator[Container]:
    try:
        await _reset_schema(TEST_DATABASE_URL)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres with pgvector is not reachable at {TEST_DATABASE_URL}: {exc}")
    await asyncio.to_thread(_migrate, TEST_DATABASE_URL)
    container = build_container(settings)
    await container.ingest.ingest(load_corpus(settings.corpus_dir))
    await load_golden_seed(container, settings.data_dir / "golden" / "seed.jsonl")
    await sync_configs(container, load_pipeline_files(settings.data_dir / "pipelines"))
    yield container
    await container.aclose()
