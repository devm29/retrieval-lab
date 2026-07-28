from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from retrieval_lab.cli import EXIT_NOT_COMPARABLE, EXIT_REGRESSED, app
from retrieval_lab.container import Container
from retrieval_lab.evals.baseline import read_baseline, write_baseline
from retrieval_lab.settings import get_settings

from .conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.db

runner = CliRunner()


@pytest.fixture
def cli_env(container: Container, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in {
        "RLAB_DATABASE_URL": TEST_DATABASE_URL,
        "RLAB_EMBEDDER": "hashing",
        "RLAB_RERANKER": "lexical",
        "RLAB_LLM_PROVIDER": "fake",
        "RLAB_LOG_LEVEL": "WARNING",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def baseline_file(cli_env: None, tmp_path: Path) -> Path:
    result = runner.invoke(app, ["eval", "baseline", "--config", "bm25", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path / "bm25.json"


def _gate(baseline: Path, *extra: str) -> int:
    result = runner.invoke(
        app, ["eval", "gate", "--config", "bm25", "--baseline", str(baseline), "--no-sync", *extra]
    )
    return result.exit_code


def test_gate_passes_against_its_own_baseline(baseline_file: Path) -> None:
    assert _gate(baseline_file) == 0


def test_gate_fails_when_ndcg_regressed(baseline_file: Path) -> None:
    stored = read_baseline(baseline_file)
    metrics = stored.summary.metrics.model_copy(update={"ndcg_at_k": 1.0})
    write_baseline(
        baseline_file,
        stored.model_copy(update={"summary": stored.summary.model_copy(update={"metrics": metrics})}),
    )
    assert _gate(baseline_file) == EXIT_REGRESSED


def test_gate_refuses_a_baseline_from_another_golden_set(baseline_file: Path) -> None:
    stored = read_baseline(baseline_file)
    assert stored.summary.environment is not None
    environment = stored.summary.environment.model_copy(update={"golden_hash": "0" * 64})
    write_baseline(
        baseline_file,
        stored.model_copy(update={"summary": stored.summary.model_copy(update={"environment": environment})}),
    )
    assert _gate(baseline_file) == EXIT_NOT_COMPARABLE
    assert _gate(baseline_file, "--allow-drift") == 0


def test_mode_is_validated(cli_env: None) -> None:
    result = runner.invoke(app, ["eval", "run", "--config", "bm25", "--mode", "retreival"])
    assert result.exit_code == 2
