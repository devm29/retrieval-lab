from __future__ import annotations

from datetime import UTC, datetime

from rich.console import Console
from sqlalchemy import func, select

from retrieval_lab.bootstrap import load_golden_seed, load_pipeline_files, sync_configs
from retrieval_lab.container import Container
from retrieval_lab.db.models import EvalRun, GoldenStatus, PipelineConfigRow
from retrieval_lab.db.session import transaction
from retrieval_lab.evals.baseline import baseline_path, write_baseline
from retrieval_lab.evals.calibration import calibrate, load_items
from retrieval_lab.evals.schemas import BaselineFile, RunSummary
from retrieval_lab.ingest.loader import load_corpus
from retrieval_lab.repositories.golden import GoldenRepository
from retrieval_lab.repositories.runs import CalibrationRepository, RunRepository
from retrieval_lab.retrieval.config import PipelineConfig

# Earlier versions of the shipped configs, so the dashboard shows how each one evolved.
HISTORY: list[dict[str, object]] = [
    {
        "name": "dense",
        "description": "First dense attempt with a shallow HNSW search.",
        "spec": {"kind": "dense", "top_k": 10, "ef_search": 16, "generation": {"abstain_below": 0.6}},
    },
    {
        "name": "hybrid-rrf",
        "description": "RRF with a small k, which over-rewards the top of each list.",
        "spec": {
            "kind": "hybrid",
            "top_k": 10,
            "bm25_k": 20,
            "dense_k": 20,
            "rrf_k": 5,
            "generation": {"abstain_below": 0.6},
        },
    },
    {
        "name": "hybrid-rerank",
        "description": "Cross-encoder over a narrow candidate pool.",
        "spec": {
            "kind": "hybrid_rerank",
            "top_k": 10,
            "bm25_k": 20,
            "dense_k": 20,
            "rrf_k": 60,
            "rerank_candidates": 12,
            "generation": {"abstain_below": 0.1},
        },
    },
]

SHOWCASE_CONFIG = "hybrid-rerank"


async def run_seed(container: Container, console: Console, *, with_history: bool, synthetic: int) -> None:
    settings = container.settings
    report = await container.ingest.ingest(load_corpus(settings.corpus_dir))
    console.print(f"Corpus: {report.chunk_total} chunks (re)indexed with {report.embedding_model}")

    created, updated = await load_golden_seed(container, settings.data_dir / "golden" / "seed.jsonl")
    console.print(f"Golden set: {created} new, {updated} updated")

    async with container.sessions() as session:
        config_count = await session.scalar(select(func.count()).select_from(PipelineConfigRow))
    if with_history and not config_count:
        history = [PipelineConfig.model_validate(item) for item in HISTORY]
        await sync_configs(container, history)
        for config in history:
            await container.runner.run(f"{config.name}@1", trigger="seed", label="initial version")
            console.print(f"History run: {config.name}@1")

    synced = await sync_configs(container, load_pipeline_files(settings.data_dir / "pipelines"))
    summaries: dict[str, tuple[EvalRun, RunSummary]] = {}
    for result in synced:
        run, summary = await container.runner.run(result.name, trigger="seed", label="seed")
        summaries[result.name] = (run, summary)
        console.print(
            f"Run {result.name}@{result.version}: nDCG {summary.metrics.ndcg_at_k}, "
            f"faithfulness {summary.metrics.faithfulness}"
        )
    await container.runner.run(SHOWCASE_CONFIG, mode="retrieval", trigger="seed", label="retrieval only")

    for name, (run, summary) in summaries.items():
        async with transaction(container.sessions) as session:
            await RunRepository(session).set_baseline(name, run.id)
        write_baseline(
            baseline_path(settings.data_dir / "baselines", name),
            BaselineFile(
                config_name=name,
                spec_hash=run.config.spec_hash,
                created_at=datetime.now(UTC),
                llm_model=run.llm_model,
                judge_model=run.judge_model,
                embedding_model=container.embedder.model_name,
                summary=summary,
            ),
        )
    console.print(f"Baselines promoted and written for {len(summaries)} configs")

    async with container.sessions() as session:
        proposed = (await GoldenRepository(session).counts())[GoldenStatus.PROPOSED.value]
    if synthetic and proposed < synthetic:
        synth = await container.synthesizer.generate(synthetic - proposed, seed=0.42)
        console.print(f"Synthetic questions proposed for review: {synth.created}")

    calibration = await calibrate(
        container.judge,
        load_items(settings.data_dir / "golden" / "judge_calibration.jsonl"),
        settings.eval_concurrency,
    )
    async with transaction(container.sessions) as session:
        await CalibrationRepository(session).add(
            judge_model=calibration.judge_model,
            sample_size=calibration.sample_size,
            kappa=calibration.kappa,
            agreement=calibration.agreement,
            payload=calibration.model_dump(mode="json"),
        )
    console.print(f"Judge calibration: kappa {calibration.kappa:.3f} ({calibration.interpretation})")
