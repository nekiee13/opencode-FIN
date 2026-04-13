from __future__ import annotations

from src.ui.services import ann_stats


def test_compute_ann_overall_stats_reports_success_ratio_and_magnitude_pct(
    monkeypatch,
) -> None:
    def _fake_build_ann_real_vs_computed_rows(*, selected_date: str, tickers):
        _ = selected_date
        _ = tickers
        return [
            {
                "Ticker": "TNX",
                "Real SGN": "+",
                "Computed SGN": "+",
                "Real Magnitude": "10.0",
                "Computed Magnitude": "8.0",
            },
            {
                "Ticker": "DJI",
                "Real SGN": "-",
                "Computed SGN": "+",
                "Real Magnitude": "20.0",
                "Computed Magnitude": "10.0",
            },
        ]

    monkeypatch.setattr(
        ann_stats,
        "build_ann_real_vs_computed_rows",
        _fake_build_ann_real_vs_computed_rows,
    )

    out = ann_stats.compute_ann_overall_stats(
        dates=["2026-04-07"],
        tickers=["TNX", "DJI"],
    )
    assert out["success_count"] == 1
    assert out["total_count"] == 2
    assert out["success_label"].startswith("1/2")

    rows = {str(x["Ticker"]): x for x in out["magnitude_ratio_rows"]}
    assert rows["TNX"]["Magnitude (% of Delta)"] == "80.00"
    assert rows["DJI"]["Magnitude (% of Delta)"] == "50.00"
