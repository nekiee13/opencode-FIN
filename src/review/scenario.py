from __future__ import annotations

from src.review.models import ScenarioResultModel

_ALLOWED_LABELS = {"Yellow", "Green", "Red", "White"}


def evaluate_scenario(
    *,
    ai_consensus_value: float | None,
    manual_prediction_override: float | None,
    prior_label: str | None,
    enable_rule: bool = False,
    green_threshold: float = 0.5,
    red_threshold: float = -0.5,
) -> ScenarioResultModel:
    if not enable_rule:
        return ScenarioResultModel(
            scenario_label=None,
            source_inputs={
                "ai_consensus_value": ai_consensus_value,
                "manual_prediction_override": manual_prediction_override,
            },
            thresholds_used={},
            reason_codes=("RULE_UNAVAILABLE",),
            changed_from_prior=False,
        )

    delta: float | None = None
    if ai_consensus_value is not None and manual_prediction_override is not None:
        delta = float(manual_prediction_override) - float(ai_consensus_value)

    if delta is None:
        label = "White"
        reason = "MISSING_VALUES"
    elif delta >= green_threshold:
        label = "Green"
        reason = "DELTA_ABOVE_GREEN"
    elif delta <= red_threshold:
        label = "Red"
        reason = "DELTA_BELOW_RED"
    else:
        label = "Yellow"
        reason = "DELTA_BETWEEN_THRESHOLDS"

    if label not in _ALLOWED_LABELS:
        label = "White"
        reason = "INVALID_LABEL_RECOVERED"

    changed = bool(prior_label) and prior_label != label
    return ScenarioResultModel(
        scenario_label=label,
        source_inputs={
            "ai_consensus_value": ai_consensus_value,
            "manual_prediction_override": manual_prediction_override,
            "delta": delta,
        },
        thresholds_used={
            "green_threshold": green_threshold,
            "red_threshold": red_threshold,
        },
        reason_codes=(reason,),
        changed_from_prior=changed,
    )
