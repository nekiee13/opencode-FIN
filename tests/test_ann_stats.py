from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from src.ui.services import ann_stats


def test_compute_ann_overall_stats_reports_success_ratio_and_delta_magnitude_gap(
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
    monkeypatch.setattr(
        ann_stats,
        "predict_ann_computed_sgn_overrides",
        lambda **kwargs: {"computed_sgn_overrides": {"TNX": "+", "DJI": "-"}},
    )
    monkeypatch.setattr(
        ann_stats,
        "build_ann_t0_p_sgn_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Computed SGN": "+",
                "Realized SGN": "+",
                "Magnitude": "8.0",
                "Delta": "10.0",
            },
            {
                "Ticker": "DJI",
                "Computed SGN": "-",
                "Realized SGN": "+",
                "Magnitude": "10.0",
                "Delta": "20.0",
            },
        ],
    )

    out = ann_stats.compute_ann_overall_stats(
        dates=["2026-04-07"],
        tickers=["TNX", "DJI"],
    )
    assert out["success_count"] == 1
    assert out["total_count"] == 2
    assert out["success_label"].startswith("1/2")

    rows = {str(x["Ticker"]): x for x in out["magnitude_gap_rows"]}
    assert rows["TNX"]["Gap (D>M%)"] == "2.00 (100% D>M)"
    assert rows["DJI"]["Gap (D>M%)"] == "10.00 (100% D>M)"


def test_compute_ann_overall_stats_uses_continuation_sgn_for_success(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ann_stats,
        "build_ann_real_vs_computed_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Real SGN": "+",
                "Computed SGN": "-",
                "Real Magnitude": "3.0",
                "Computed Magnitude": "2.0",
            }
        ],
    )
    monkeypatch.setattr(
        ann_stats,
        "predict_ann_computed_sgn_overrides",
        lambda **kwargs: {"computed_sgn_overrides": {"TNX": "-"}},
    )
    monkeypatch.setattr(
        ann_stats,
        "build_ann_t0_p_sgn_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Computed SGN": "-",
                "Realized SGN": "-",
                "Magnitude": "2.0",
                "Delta": "3.0",
            }
        ],
    )

    out = ann_stats.compute_ann_overall_stats(
        dates=["2026-04-07"],
        tickers=["TNX"],
    )

    assert out["success_count"] == 1
    assert out["total_count"] == 1
    assert out["success_label"].startswith("1/1")


def test_compute_ann_overall_stats_emits_failed_and_mag_gt_delta_logs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ann_stats,
        "build_ann_real_vs_computed_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Real SGN": "+",
                "Computed SGN": "+",
                "Real Magnitude": "5.0",
                "Computed Magnitude": "10.0",
            }
        ],
    )
    monkeypatch.setattr(
        ann_stats,
        "predict_ann_computed_sgn_overrides",
        lambda **kwargs: {"computed_sgn_overrides": {"TNX": "+"}},
    )
    monkeypatch.setattr(
        ann_stats,
        "build_ann_t0_p_sgn_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Computed SGN": "+",
                "Realized SGN": "-",
                "Magnitude": "10.0",
                "Delta": "5.0",
            }
        ],
    )

    out = ann_stats.compute_ann_overall_stats(
        dates=["2026-04-07"],
        tickers=["TNX"],
    )

    assert out["failed_sgn_count"] == 1
    assert len(out["failed_sgn_rows"]) == 1
    assert out["failed_sgn_rows"][0]["Date"] == "2026-04-07"
    assert out["failed_sgn_rows"][0]["Ticker"] == "TNX"

    assert out["magnitude_gt_delta_count"] == 1
    assert len(out["magnitude_gt_delta_rows"]) == 1
    assert out["magnitude_gt_delta_rows"][0]["Date"] == "2026-04-07"
    assert out["magnitude_gt_delta_rows"][0]["Ticker"] == "TNX"
    assert out["magnitude_gt_delta_rows"][0]["Ratio (% of Delta)"] == "200.00"


def test_compute_ann_overall_stats_writes_magnitude_delta_log_file(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ann_stats,
        "build_ann_real_vs_computed_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Real SGN": "+",
                "Computed SGN": "+",
                "Real Magnitude": "5.0",
                "Computed Magnitude": "10.0",
            }
        ],
    )
    monkeypatch.setattr(
        ann_stats,
        "predict_ann_computed_sgn_overrides",
        lambda **kwargs: {"computed_sgn_overrides": {"TNX": "+"}},
    )
    monkeypatch.setattr(
        ann_stats,
        "build_ann_t0_p_sgn_rows",
        lambda **kwargs: [
            {
                "Ticker": "TNX",
                "Computed SGN": "+",
                "Realized SGN": "+",
                "Magnitude": "10.0",
                "Delta": "5.0",
            }
        ],
    )

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out = ann_stats.compute_ann_overall_stats(
            dates=["2026-04-07"],
            tickers=["TNX"],
            log_dir=tmp_path,
        )

        log_path = tmp_path / "Magnitude _Delta.log"
        assert out["magnitude_delta_log_path"] == str(log_path)
        assert log_path.exists()
        text = log_path.read_text(encoding="utf-8")
        assert "2026-04-07" in text
        assert "TNX" in text
        assert "10.0000" in text
        assert "5.0000" in text
