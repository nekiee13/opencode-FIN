from __future__ import annotations

from src.ui.services.ann_sgn_map import (
    build_sgn_probability_map_from_samples,
    classify_sgn_case,
)


def test_classify_sgn_case_maps_four_class_grid() -> None:
    assert classify_sgn_case(real_sgn="+", computed_sgn="+") == "pp"
    assert classify_sgn_case(real_sgn="+", computed_sgn="-") == "pn"
    assert classify_sgn_case(real_sgn="-", computed_sgn="+") == "np"
    assert classify_sgn_case(real_sgn="-", computed_sgn="-") == "nn"
    assert classify_sgn_case(real_sgn="0", computed_sgn="+") is None
    assert classify_sgn_case(real_sgn="", computed_sgn="-") is None


def test_build_sgn_probability_map_from_samples_returns_regions_confidence_and_metrics() -> (
    None
):
    samples = [
        {
            "as_of_date": "2026-03-01",
            "ticker": "TNX",
            "class_id": "pp",
            "features": {"f1": 1.2, "f2": 1.1, "f3": 0.1, "f4": 0.0},
        },
        {
            "as_of_date": "2026-03-02",
            "ticker": "TNX",
            "class_id": "pp",
            "features": {"f1": 1.4, "f2": 1.3, "f3": 0.2, "f4": 0.1},
        },
        {
            "as_of_date": "2026-03-03",
            "ticker": "TNX",
            "class_id": "pn",
            "features": {"f1": 1.3, "f2": -1.2, "f3": 0.1, "f4": -0.1},
        },
        {
            "as_of_date": "2026-03-04",
            "ticker": "TNX",
            "class_id": "pn",
            "features": {"f1": 1.1, "f2": -1.4, "f3": 0.0, "f4": -0.2},
        },
        {
            "as_of_date": "2026-03-05",
            "ticker": "TNX",
            "class_id": "np",
            "features": {"f1": -1.2, "f2": 1.1, "f3": -0.1, "f4": 0.2},
        },
        {
            "as_of_date": "2026-03-06",
            "ticker": "TNX",
            "class_id": "np",
            "features": {"f1": -1.3, "f2": 1.2, "f3": -0.2, "f4": 0.1},
        },
        {
            "as_of_date": "2026-03-07",
            "ticker": "TNX",
            "class_id": "nn",
            "features": {"f1": -1.1, "f2": -1.2, "f3": -0.1, "f4": -0.1},
        },
        {
            "as_of_date": "2026-03-08",
            "ticker": "TNX",
            "class_id": "nn",
            "features": {"f1": -1.4, "f2": -1.1, "f3": -0.2, "f4": -0.2},
        },
    ]

    out = build_sgn_probability_map_from_samples(
        ticker="TNX",
        samples=samples,
        grid_size=10,
        max_features=4,
        k_neighbors=3,
        edge_threshold=0.60,
        rolling_window=4,
    )

    assert out["ticker"] == "TNX"
    assert out["point_count"] == 8
    assert len(out["points"]) == 8
    assert len(out["grid"]) == 100
    assert set(out["class_order"]) == {"pp", "pn", "np", "nn"}
    assert set(out["weights"].keys()) == {"U", "V"}

    point_probs = [float(row["max_prob"]) for row in out["points"]]
    grid_probs = [float(row["max_prob"]) for row in out["grid"]]
    assert min(point_probs) >= 0.0
    assert max(point_probs) <= 1.0
    assert min(grid_probs) >= 0.0
    assert max(grid_probs) <= 1.0

    metrics = out["metrics"]
    assert float(metrics["agreement_rate"]) >= 0.75
    assert int(metrics["sample_count"]) == 8
    assert "edge_accuracy" in metrics
    assert "macro_f1" in metrics
