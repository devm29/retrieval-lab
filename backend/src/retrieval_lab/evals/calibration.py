from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from retrieval_lab.evals.judge import Judge
from retrieval_lab.evals.kappa import cohens_kappa, confusion_matrix, interpret_kappa, percent_agreement
from retrieval_lab.evals.schemas import CalibrationItem, CalibrationOutcome, CalibrationReport
from retrieval_lab.llm.base import TokenUsage

Label = Literal["faithful", "unfaithful"]
LABELS: tuple[Label, Label] = ("faithful", "unfaithful")


def load_items(path: Path) -> list[CalibrationItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [CalibrationItem.model_validate(json.loads(line)) for line in lines if line.strip()]


async def calibrate(judge: Judge, items: list[CalibrationItem], concurrency: int = 4) -> CalibrationReport:
    """Score the judge against human faithfulness labels and report Cohen's kappa."""
    if not items:
        raise ValueError("calibration set is empty")
    semaphore = asyncio.Semaphore(concurrency)

    async def judge_one(item: CalibrationItem) -> tuple[CalibrationOutcome, TokenUsage]:
        async with semaphore:
            judgement = await judge.faithfulness(item.question, item.answer, item.contexts)
        label: Label = "faithful" if judgement.faithful else "unfaithful"
        outcome = CalibrationOutcome(
            id=item.id,
            question=item.question,
            answer=item.answer,
            human_label=item.human_label,
            judge_label=label,
            judge_score=judgement.score,
            claims=judgement.verdict.claims,
            agree=label == item.human_label,
            note=item.note,
        )
        return outcome, judgement.usage

    judged = await asyncio.gather(*(judge_one(item) for item in items))
    outcomes = [o for o, _ in judged]
    usage = TokenUsage()
    for _, used in judged:
        usage = usage + used
    human = [o.human_label for o in outcomes]
    machine = [o.judge_label for o in outcomes]
    kappa = cohens_kappa(human, machine)
    matrix = confusion_matrix(human, machine)
    return CalibrationReport(
        judge_model=judge.model,
        sample_size=len(outcomes),
        kappa=round(kappa, 4),
        agreement=round(percent_agreement(human, machine), 4),
        interpretation=interpret_kappa(kappa),
        confusion={h: {m: matrix.get((h, m), 0) for m in LABELS} for h in LABELS},
        items=outcomes,
        usage=usage,
    )
