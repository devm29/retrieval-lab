from __future__ import annotations

from pathlib import Path

from retrieval_lab.evals.schemas import (
    AggregateMetrics,
    BaselineFile,
    DriftItem,
    GateResult,
    GateTolerance,
    MetricDelta,
    RunEnvironment,
    RunSummary,
)

REPORTED_METRICS: tuple[str, ...] = tuple(AggregateMetrics.model_fields)
LOWER_IS_BETTER = frozenset({"false_abstention_rate"})


def drift(
    baseline: RunSummary,
    candidate: RunSummary,
    *,
    spec_hashes: tuple[str, str] | None = None,
) -> list[DriftItem]:
    """What differs between two runs besides the pipeline. Blocking drift voids the metric diff."""
    items: list[DriftItem] = []
    if baseline.k != candidate.k:
        items.append(
            DriftItem(field="k", baseline=str(baseline.k), candidate=str(candidate.k), blocking=True)
        )
    before, after = baseline.environment, candidate.environment
    if before is None or after is None:
        items.append(
            DriftItem(
                field="environment",
                baseline=None if before is None else "recorded",
                candidate=None if after is None else "recorded",
                blocking=True,
            )
        )
    else:
        for field in RunEnvironment.model_fields:
            old, new = getattr(before, field), getattr(after, field)
            if old != new:
                items.append(DriftItem(field=field, baseline=old, candidate=new, blocking=True))
    if spec_hashes is not None and spec_hashes[0] != spec_hashes[1]:
        # Expected when the gate is doing its job on a config change, so it only informs.
        old_hash, new_hash = spec_hashes
        items.append(
            DriftItem(field="spec_hash", baseline=old_hash[:12], candidate=new_hash[:12], blocking=False)
        )
    return items


def compare(
    baseline: RunSummary,
    candidate: RunSummary,
    tolerance: GateTolerance,
    *,
    config_name: str,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
    spec_hashes: tuple[str, str] | None = None,
) -> GateResult:
    """Gate on absolute drops in the tolerance-tracked metrics; report the rest."""
    gated = tolerance.model_dump()
    deltas: list[MetricDelta] = []
    for metric in REPORTED_METRICS:
        before: float | None = getattr(baseline.metrics, metric)
        after: float | None = getattr(candidate.metrics, metric)
        delta = None if before is None or after is None else round(after - before, 6)
        limit: float | None = gated.get(metric)
        regressed = False
        if limit is not None and before is not None:
            # A metric that disappeared (e.g. retrieval-only run against a full baseline) fails closed.
            regressed = after is None or (delta is not None and _worse(metric, delta, limit))
        deltas.append(
            MetricDelta(
                metric=metric,
                baseline=before,
                candidate=after,
                delta=delta,
                tolerance=limit,
                regressed=regressed,
            )
        )
    return GateResult(
        passed=not any(d.regressed for d in deltas),
        config_name=config_name,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        tolerance=tolerance,
        deltas=deltas,
        drift=drift(baseline, candidate, spec_hashes=spec_hashes),
    )


def _worse(metric: str, delta: float, limit: float) -> bool:
    drop = delta if metric in LOWER_IS_BETTER else -delta
    return drop > limit + 1e-9


def baseline_path(directory: Path, config_name: str) -> Path:
    return directory / f"{config_name}.json"


def read_baseline(path: Path) -> BaselineFile:
    return BaselineFile.model_validate_json(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, baseline: BaselineFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(baseline.model_dump_json(indent=2) + "\n", encoding="utf-8")
