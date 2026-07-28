from __future__ import annotations

import asyncio
import enum
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.table import Table

from retrieval_lab.bootstrap import load_golden_seed, load_pipeline_files, sync_configs
from retrieval_lab.container import Container, build_container
from retrieval_lab.db.models import EvalRun, RunStatus
from retrieval_lab.db.session import transaction
from retrieval_lab.evals.baseline import baseline_path, compare, read_baseline, write_baseline
from retrieval_lab.evals.calibration import calibrate, load_items
from retrieval_lab.evals.schemas import BaselineFile, GateResult, GateTolerance, RunMode, RunSummary
from retrieval_lab.ingest.loader import load_corpus
from retrieval_lab.log import configure_logging
from retrieval_lab.repositories.configs import ConfigRepository, spec_of
from retrieval_lab.repositories.runs import CalibrationRepository, RunRepository
from retrieval_lab.settings import PROJECT_ROOT, get_settings

app = typer.Typer(help="Retrieval Lab: hybrid RAG with a measurable eval harness.", no_args_is_help=True)
configs_app = typer.Typer(help="Pipeline configs.", no_args_is_help=True)
golden_app = typer.Typer(help="Golden question set.", no_args_is_help=True)
eval_app = typer.Typer(help="Evaluation runs and the regression gate.", no_args_is_help=True)
judge_app = typer.Typer(help="LLM-as-judge calibration.", no_args_is_help=True)
db_app = typer.Typer(help="Database schema.", no_args_is_help=True)
app.add_typer(configs_app, name="configs")
app.add_typer(golden_app, name="golden")
app.add_typer(eval_app, name="eval")
app.add_typer(judge_app, name="judge")
app.add_typer(db_app, name="db")

console = Console()

EXIT_REGRESSED = 1
EXIT_NOT_COMPARABLE = 2


class ModeChoice(enum.StrEnum):
    full = "full"
    retrieval = "retrieval"


def _run[T](work: Callable[[Container], Awaitable[T]]) -> T:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    async def main() -> T:
        container = build_container(settings)
        try:
            return await work(container)
        finally:
            await container.aclose()

    return asyncio.run(main())


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _summary_table(title: str, summary: RunSummary) -> Table:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for name, value in summary.metrics.model_dump().items():
        table.add_row(name, _fmt(value))
    for stage, stats in summary.latency_ms.items():
        table.add_row(f"latency {stage} p50/p95 ms", f"{stats.p50:.1f} / {stats.p95:.1f}")
    table.add_row("cost per query (USD)", f"{summary.cost_per_query_usd:.5f}")
    return table


def _gate_table(result: GateResult) -> Table:
    table = Table(title=f"Gate: {result.config_name}", header_style="bold")
    for column in ("metric", "baseline", "candidate", "delta", "tolerance", "status"):
        table.add_column(column, justify="left" if column == "metric" else "right")
    for d in result.deltas:
        status = "[red]regressed[/red]" if d.regressed else ("gated" if d.tolerance is not None else "")
        delta = "—" if d.delta is None else f"{d.delta:+.3f}"
        table.add_row(d.metric, _fmt(d.baseline), _fmt(d.candidate), delta, _fmt(d.tolerance), status)
    return table


def _drift_table(result: GateResult) -> Table:
    table = Table(title="Not the same experiment", header_style="bold")
    for column in ("field", "baseline", "candidate", ""):
        table.add_column(column)
    for d in result.drift:
        table.add_row(d.field, d.baseline or "—", d.candidate or "—", "blocking" if d.blocking else "note")
    return table


def _completed_summary(run: EvalRun) -> RunSummary:
    if run.status is not RunStatus.COMPLETED or not run.summary:
        console.print(f"[red]Run {run.id} is {run.status.value}; only completed runs have a summary.[/red]")
        raise typer.Exit(code=1)
    return RunSummary.model_validate(run.summary)


def gate_markdown(result: GateResult) -> str:
    verdict = "passed" if result.passed else "failed"
    lines = [
        f"### Retrieval quality gate {verdict}: `{result.config_name}`",
        "",
        f"Baseline `{result.baseline_label}` vs candidate `{result.candidate_label}`.",
        "",
        "| metric | baseline | candidate | delta | tolerance | |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for d in result.deltas:
        delta = "—" if d.delta is None else f"{d.delta:+.3f}"
        flag = "regressed" if d.regressed else ("gated" if d.tolerance is not None else "")
        cells = [d.metric, _fmt(d.baseline), _fmt(d.candidate), delta, _fmt(d.tolerance), flag]
        lines.append("| " + " | ".join(cells) + " |")
    if result.drift:
        lines += ["", "| differs from baseline | baseline | candidate | |", "|---|---|---|---|"]
        for item in result.drift:
            kind = "blocking" if item.blocking else "note"
            lines.append(f"| {item.field} | {item.baseline or '—'} | {item.candidate or '—'} | {kind} |")
    return "\n".join(lines) + "\n"


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply Alembic migrations."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(PROJECT_ROOT / "backend" / "alembic.ini")), "head")
    console.print("[green]Schema is up to date.[/green]")


@app.command()
def ingest(
    corpus: Annotated[Path | None, typer.Option(help="Directory of .md/.txt files.")] = None,
    force: Annotated[bool, typer.Option(help="Re-chunk and re-embed unchanged documents.")] = False,
) -> None:
    """Chunk, embed and index the corpus."""

    async def work(c: Container) -> None:
        report = await c.ingest.ingest(load_corpus(corpus or c.settings.corpus_dir), force=force)
        for doc in report.documents:
            state = "unchanged" if doc.skipped else f"{doc.chunks} chunks"
            console.print(f"  {doc.slug:<32} {state}")
        console.print(
            f"[green]Indexed {report.chunk_total} chunks with {report.embedding_model} "
            f"in {report.seconds}s[/green] (removed {report.removed} stale documents)"
        )

    _run(work)


@configs_app.command("sync")
def configs_sync(
    directory: Annotated[Path | None, typer.Option(help="Directory of pipeline JSON files.")] = None,
) -> None:
    """Register pipeline configs; a changed spec becomes a new version."""

    async def work(c: Container) -> None:
        for result in await sync_configs(
            c, load_pipeline_files(directory or c.settings.data_dir / "pipelines")
        ):
            marker = "new" if result.created else "unchanged"
            console.print(f"  {result.name}@{result.version}  {result.spec_hash[:12]}  {marker}")

    _run(work)


@configs_app.command("list")
def configs_list() -> None:
    async def work(c: Container) -> None:
        async with c.sessions() as session:
            rows = await ConfigRepository(session).list_all()
        table = Table(header_style="bold")
        for column in ("name", "version", "kind", "hash"):
            table.add_column(column)
        for row in rows:
            table.add_row(row.name, str(row.version), row.kind, row.spec_hash[:12])
        console.print(table)

    _run(work)


@golden_app.command("load")
def golden_load(path: Annotated[Path | None, typer.Option(help="Seed JSONL file.")] = None) -> None:
    """Upsert the curated seed golden set."""

    async def work(c: Container) -> None:
        created, updated = await load_golden_seed(c, path or c.settings.data_dir / "golden" / "seed.jsonl")
        console.print(f"[green]Golden seed loaded:[/green] {created} new, {updated} updated")

    _run(work)


@golden_app.command("synth")
def golden_synth(
    count: Annotated[int, typer.Option(min=1, max=200)] = 10,
    document: Annotated[str | None, typer.Option(help="Restrict to one document slug.")] = None,
) -> None:
    """Generate synthetic questions from random chunks; they land in the review queue."""

    async def work(c: Container) -> None:
        report = await c.synthesizer.generate(count, document_slug=document)
        console.print(
            f"[green]{report.created} proposed[/green], {report.skipped} skipped, "
            f"${report.usage.cost_usd:.4f} ({c.llm.model})"
        )

    _run(work)


@app.command()
def ask(
    question: str,
    config: Annotated[str, typer.Option(help="Config name, name@version or id.")] = "hybrid-rerank",
) -> None:
    """Answer one question and show citations and stage timings."""

    async def work(c: Container) -> None:
        async with c.sessions() as session:
            row = await ConfigRepository(session).resolve(config)
        result = await c.answers.answer(question, c.pipeline(spec_of(row)))
        console.print(f"\n[bold]{result.answer.text}[/bold]\n")
        for citation in result.answer.citations:
            console.print(f"  [{citation.marker}] {citation.chunk_id}  {citation.heading}")
        timings = ", ".join(f"{k} {v:.0f}ms" for k, v in result.timings_ms.items())
        console.print(f"\n[dim]{row.name}@{row.version} · {timings}[/dim]")

    _run(work)


async def _run_eval(
    c: Container, config: str, mode: RunMode, label: str | None, k: int | None, trigger: Literal["cli", "ci"]
) -> tuple[uuid.UUID, str, str, RunSummary]:
    run, summary = await c.runner.run(config, mode=mode, trigger=trigger, label=label, k=k)
    return run.id, run.config.name, run.config.spec_hash, summary


@eval_app.command("run")
def eval_run(
    config: Annotated[str, typer.Option(help="Config name, name@version or id.")] = "hybrid-rerank",
    mode: Annotated[ModeChoice, typer.Option(help="Score answers too, or retrieval only.")] = ModeChoice.full,
    k: Annotated[
        int | None, typer.Option(help="Cut-off for @k metrics; defaults to the config's top_k.")
    ] = None,
    label: Annotated[str | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option(help="Write the run summary as JSON.")] = None,
) -> None:
    """Evaluate one config against the accepted golden set."""
    run_mode: RunMode = "retrieval" if mode is ModeChoice.retrieval else "full"

    async def work(c: Container) -> None:
        run_id, name, _, summary = await _run_eval(c, config, run_mode, label, k, "cli")
        console.print(_summary_table(f"{name} · run {run_id}", summary))
        if output:
            output.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    _run(work)


@eval_app.command("baseline")
def eval_baseline(
    config: Annotated[str, typer.Option()] = "hybrid-rerank",
    run_id: Annotated[
        uuid.UUID | None, typer.Option("--run", help="Promote this run instead of running a new one.")
    ] = None,
    directory: Annotated[Path | None, typer.Option(help="Where baseline JSON files live.")] = None,
) -> None:
    """Promote a run to baseline in the database and write the baseline file used by CI."""

    async def work(c: Container) -> None:
        if run_id is None:
            new_id, _, _, _ = await _run_eval(c, config, "full", "baseline", None, "cli")
        else:
            new_id = run_id
        async with transaction(c.sessions) as session:
            runs = RunRepository(session)
            run = await runs.get(new_id)
            summary = _completed_summary(run)
            if summary.mode != "full":
                console.print("[red]Only full runs (with generation metrics) can become a baseline.[/red]")
                raise typer.Exit(code=1)
            await runs.set_baseline(run.config.name, run.id)
        baseline = BaselineFile(
            config_name=run.config.name,
            spec_hash=run.config.spec_hash,
            created_at=datetime.now(UTC),
            llm_model=run.llm_model,
            judge_model=run.judge_model,
            embedding_model=c.embedder.model_name,
            summary=summary,
        )
        path = baseline_path(directory or c.settings.data_dir / "baselines", run.config.name)
        write_baseline(path, baseline)
        console.print(f"[green]Baseline for {run.config.name} written to {path}[/green]")

    _run(work)


@eval_app.command("gate")
def eval_gate(
    config: Annotated[str, typer.Option()] = "hybrid-rerank",
    baseline: Annotated[
        Path | None, typer.Option(help="Baseline JSON; defaults to data/baselines/<config>.json")
    ] = None,
    tolerance_ndcg: Annotated[float, typer.Option(min=0)] = 0.02,
    tolerance_faithfulness: Annotated[float, typer.Option(min=0)] = 0.03,
    report: Annotated[
        Path | None, typer.Option(help="Append a markdown report (e.g. $GITHUB_STEP_SUMMARY).")
    ] = None,
    sync: Annotated[bool, typer.Option(help="Sync pipeline files before running.")] = True,
    allow_drift: Annotated[
        bool,
        typer.Option(help="Compare even if the models, k or golden set differ from the baseline's."),
    ] = False,
) -> None:
    """Run an eval and exit non-zero if nDCG or faithfulness dropped beyond tolerance.

    Exit codes: 1 when a gated metric regressed, 2 when the run is not comparable with the
    baseline (different models, k or golden set) and --allow-drift was not given.
    """
    tolerance = GateTolerance(ndcg_at_k=tolerance_ndcg, faithfulness=tolerance_faithfulness)

    async def work(c: Container) -> GateResult:
        if sync:
            await sync_configs(c, load_pipeline_files(c.settings.data_dir / "pipelines"))
        stored = read_baseline(baseline or baseline_path(c.settings.data_dir / "baselines", config))
        run_id, name, digest, summary = await _run_eval(c, config, "full", "gate", stored.summary.k, "ci")
        result = compare(
            stored.summary,
            summary,
            tolerance,
            config_name=name,
            baseline_label=f"{stored.config_name}@{stored.spec_hash[:12]}",
            candidate_label=f"{name}@{digest[:12]} (run {str(run_id)[:8]})",
            spec_hashes=(stored.spec_hash, digest),
        )
        console.print(_gate_table(result))
        if result.drift:
            console.print(_drift_table(result))
        return result

    result = _run(work)
    if report:
        with report.open("a", encoding="utf-8") as handle:
            handle.write(gate_markdown(result))
    if not result.comparable and not allow_drift:
        console.print(
            "[red]The baseline was recorded with different models, k or golden set, so the diff is "
            "meaningless.[/red] Regenerate it with `rlab eval baseline`, or pass --allow-drift."
        )
        raise typer.Exit(code=EXIT_NOT_COMPARABLE)
    if not result.passed:
        console.print("[red]Quality gate failed.[/red]")
        raise typer.Exit(code=EXIT_REGRESSED)
    console.print("[green]Quality gate passed.[/green]")


@eval_app.command("compare")
def eval_compare(
    baseline_run: Annotated[uuid.UUID, typer.Argument(help="Baseline run id.")],
    candidate_run: Annotated[uuid.UUID, typer.Argument(help="Candidate run id.")],
    tolerance_ndcg: Annotated[float, typer.Option(min=0)] = 0.02,
    tolerance_faithfulness: Annotated[float, typer.Option(min=0)] = 0.03,
) -> None:
    """Diff two stored runs without re-running anything."""

    async def work(c: Container) -> GateResult:
        async with c.sessions() as session:
            runs = RunRepository(session)
            before = await runs.get(baseline_run)
            after = await runs.get(candidate_run)
        return compare(
            _completed_summary(before),
            _completed_summary(after),
            GateTolerance(ndcg_at_k=tolerance_ndcg, faithfulness=tolerance_faithfulness),
            config_name=after.config.name,
            baseline_label=str(baseline_run)[:8],
            candidate_label=str(candidate_run)[:8],
            spec_hashes=(before.config.spec_hash, after.config.spec_hash),
        )

    result = _run(work)
    console.print(_gate_table(result))
    if result.drift:
        console.print(_drift_table(result))
    if not result.passed:
        raise typer.Exit(code=EXIT_REGRESSED)


@judge_app.command("calibrate")
def judge_calibrate(path: Annotated[Path | None, typer.Option(help="Human-labelled JSONL.")] = None) -> None:
    """Compare judge verdicts with human labels and report Cohen's kappa."""

    async def work(c: Container) -> None:
        items = load_items(path or c.settings.data_dir / "golden" / "judge_calibration.jsonl")
        report = await calibrate(c.judge, items, c.settings.eval_concurrency)
        async with transaction(c.sessions) as session:
            await CalibrationRepository(session).add(
                judge_model=report.judge_model,
                sample_size=report.sample_size,
                kappa=report.kappa,
                agreement=report.agreement,
                payload=report.model_dump(mode="json"),
            )
        console.print(
            f"Judge {report.judge_model}: kappa [bold]{report.kappa:.3f}[/bold] ({report.interpretation}), "
            f"agreement {report.agreement:.0%} over {report.sample_size} items"
        )
        console.print_json(json.dumps(report.confusion))

    _run(work)


@app.command()
def seed(
    with_history: Annotated[
        bool, typer.Option(help="Also create earlier config versions and their runs.")
    ] = True,
    synthetic: Annotated[int, typer.Option(help="Synthetic questions to leave in the review queue.")] = 12,
) -> None:
    """Load everything the dashboard needs: corpus, configs, golden set, runs, baselines, calibration."""
    from retrieval_lab.seed import run_seed

    _run(lambda c: run_seed(c, console, with_history=with_history, synthetic=synthetic))


if __name__ == "__main__":
    app()
