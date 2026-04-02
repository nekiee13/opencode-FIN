from __future__ import annotations

from statistics import mean

from src.review.models import ConsensusResultModel, ModelComparisonRowModel


def _sgn(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "+"
    if value < 0:
        return "-"
    return "+"


def compute_review_consensus(
    *,
    review_date: str,
    ticker: str,
    rows: list[ModelComparisonRowModel],
    strategy_name: str = "policy_selected",
) -> ConsensusResultModel:
    selected_rows = [
        row for row in rows if row.selected and row.prediction_value is not None
    ]
    usable_rows = [row for row in rows if row.prediction_value is not None]

    if selected_rows:
        consensus_value = float(selected_rows[0].prediction_value)
        contributing = tuple(row.model_name for row in selected_rows)
        excluded = tuple(
            row.model_name for row in rows if row.model_name not in set(contributing)
        )
        notes = "Consensus uses selected model output."
    elif usable_rows:
        consensus_value = float(
            mean(float(row.prediction_value) for row in usable_rows)
        )
        contributing = tuple(row.model_name for row in usable_rows)
        excluded = tuple()
        notes = "Consensus falls back to mean of available model outputs."
    else:
        consensus_value = None
        contributing = tuple()
        excluded = tuple(row.model_name for row in rows)
        notes = "No usable model predictions were available."

    return ConsensusResultModel(
        ticker=ticker,
        review_date=review_date,
        consensus_value=consensus_value,
        consensus_sgn=_sgn(consensus_value),
        strategy_name=strategy_name,
        contributing_models=contributing,
        excluded_models=excluded,
        source_artifacts=tuple(),
        notes=notes,
    )
