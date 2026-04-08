from __future__ import annotations

from pathlib import Path

from src.ui.services import batch_chain


def test_select_processing_dates_sorts_ascending_and_filters_range() -> None:
    dates = [
        "2026-03-31",
        "2025-07-29",
        "2025-08-05",
        "2025-08-05",
        "2026-01-01",
    ]
    out = batch_chain.select_processing_dates(
        available_dates=dates,
        start_date="2025-07-29",
        end_date="2025-12-31",
    )
    assert out == ["2025-07-29", "2025-08-05"]


def test_run_full_chain_for_date_happy_path(monkeypatch, tmp_path: Path) -> None:
    class _Spec:
        def __init__(
            self, stage: str, category: str = "core", ticker: str | None = "TNX"
        ) -> None:
            self.stage = stage
            self.category = category
            self.ticker = ticker

    class _Result:
        def __init__(self, stage: str) -> None:
            self.returncode = 0
            self.duration_seconds = 0.1
            self.stdout = "ok"
            self.stderr = ""
            self.spec = _Spec(stage)

    monkeypatch.setattr(
        batch_chain,
        "build_pipeline_commands",
        lambda **kwargs: [
            _Spec("svl_export", "core", "TNX"),
            _Spec("make_fh3_table", "core", "ALL"),
        ],
    )
    monkeypatch.setattr(batch_chain, "run_command", lambda spec: _Result(spec.stage))
    monkeypatch.setattr(
        batch_chain,
        "run_anchored_backfill",
        lambda **kwargs: {
            "status": "success",
            "index_code": "BACKFILL_OK",
            "forecast_date": "2025-07-30",
        },
    )
    monkeypatch.setattr(
        batch_chain,
        "materialize_for_selected_date",
        lambda **kwargs: {"forecast_date": "2025-07-30", "policy_mode": "step_floor"},
    )
    monkeypatch.setattr(
        batch_chain,
        "evaluate_pipeline_state",
        lambda **kwargs: {"index_code": "QA_OK", "selected_date": "2025-07-29"},
    )
    monkeypatch.setattr(
        batch_chain,
        "write_pipeline_qa_log",
        lambda *, report, root_dir=None: tmp_path / "qa.json",
    )

    out = batch_chain.run_full_chain_for_date(
        selected_date="2025-07-29",
        selected_ticker="ALL",
        run_load_blue_green=True,
    )

    assert out["selected_date"] == "2025-07-29"
    assert out["pipeline_ok"] is True
    assert out["backfill_ok"] is True
    assert out["load_blue_green_ok"] is True
    assert out["qa_index_code"] == "QA_OK"
    assert out["overall_status"] == "success"


def test_run_full_chain_for_date_stops_after_pipeline_failure(monkeypatch) -> None:
    class _Spec:
        def __init__(
            self, stage: str, category: str = "core", ticker: str | None = "TNX"
        ) -> None:
            self.stage = stage
            self.category = category
            self.ticker = ticker

    class _Result:
        def __init__(self, stage: str, rc: int) -> None:
            self.returncode = rc
            self.duration_seconds = 0.1
            self.stdout = ""
            self.stderr = "boom"
            self.spec = _Spec(stage)

    monkeypatch.setattr(
        batch_chain,
        "build_pipeline_commands",
        lambda **kwargs: [
            _Spec("svl_export", "core", "TNX"),
            _Spec("make_fh3_table", "core", "ALL"),
        ],
    )

    def _runner(spec):
        if spec.stage == "make_fh3_table":
            return _Result(spec.stage, 2)
        return _Result(spec.stage, 0)

    monkeypatch.setattr(batch_chain, "run_command", _runner)

    out = batch_chain.run_full_chain_for_date(
        selected_date="2025-07-29",
        selected_ticker="ALL",
        run_load_blue_green=True,
    )

    assert out["pipeline_ok"] is False
    assert out["backfill_ok"] is False
    assert out["load_blue_green_ok"] is False
    assert out["overall_status"] == "pipeline_failed"


def test_run_full_chain_for_date_records_pipeline_run(
    monkeypatch, tmp_path: Path
) -> None:
    class _Spec:
        def __init__(
            self,
            stage: str,
            category: str = "core",
            ticker: str | None = "TNX",
        ) -> None:
            self.stage = stage
            self.category = category
            self.ticker = ticker
            self.command = ["python", "-m", stage]

    class _Result:
        def __init__(self, stage: str) -> None:
            self.returncode = 0
            self.duration_seconds = 0.2
            self.stdout = f"ok-{stage}"
            self.stderr = ""
            self.spec = _Spec(stage)

    created: dict[str, object] = {}
    appended: list[dict[str, object]] = []
    finalized: list[str] = []

    monkeypatch.setattr(
        batch_chain,
        "build_pipeline_commands",
        lambda **kwargs: [
            _Spec("svl_export", "core", "TNX"),
            _Spec("make_fh3_table", "core", "ALL"),
        ],
    )
    monkeypatch.setattr(batch_chain, "run_command", lambda spec: _Result(spec.stage))
    monkeypatch.setattr(
        batch_chain,
        "run_anchored_backfill",
        lambda **kwargs: {
            "status": "success",
            "index_code": "BACKFILL_OK",
            "forecast_date": "2025-07-30",
        },
    )
    monkeypatch.setattr(
        batch_chain,
        "materialize_for_selected_date",
        lambda **kwargs: {"forecast_date": "2025-07-30", "policy_mode": "step_floor"},
    )
    monkeypatch.setattr(
        batch_chain,
        "evaluate_pipeline_state",
        lambda **kwargs: {"index_code": "QA_OK", "selected_date": "2025-07-29"},
    )
    monkeypatch.setattr(
        batch_chain,
        "write_pipeline_qa_log",
        lambda *, report, root_dir=None: tmp_path / "qa.json",
    )

    def _create_run(**kwargs):
        created.update(kwargs)
        return {"run_id": "RUN-TEST-1"}

    def _append_stage_result(**kwargs):
        appended.append(kwargs)
        return kwargs

    def _finalize_run(run_id: str, root_dir=None):
        _ = root_dir
        finalized.append(run_id)
        return {"run_id": run_id, "status": "success"}

    monkeypatch.setattr(batch_chain, "create_run", _create_run, raising=False)
    monkeypatch.setattr(
        batch_chain, "append_stage_result", _append_stage_result, raising=False
    )
    monkeypatch.setattr(batch_chain, "finalize_run", _finalize_run, raising=False)

    out = batch_chain.run_full_chain_for_date(
        selected_date="2025-07-29",
        selected_ticker="ALL",
        run_load_blue_green=True,
    )

    assert out["overall_status"] == "success"
    assert created["selected_date"] == "2025-07-29"
    assert created["selected_ticker"] == "ALL"
    assert created["total_stages"] == 2
    assert len(appended) == 2
    assert [x["stage_index"] for x in appended] == [1, 2]
    assert finalized == ["RUN-TEST-1"]


def test_run_full_chain_for_dates_emits_progress(monkeypatch) -> None:
    events: list[dict[str, object]] = []

    results = {
        "2025-07-29": {"selected_date": "2025-07-29", "overall_status": "success"},
        "2025-07-30": {"selected_date": "2025-07-30", "overall_status": "qa_not_ok"},
    }

    monkeypatch.setattr(
        batch_chain,
        "run_full_chain_for_date",
        lambda *, selected_date, **kwargs: results[str(selected_date)],
    )

    out = batch_chain.run_full_chain_for_dates(
        dates=["2025-07-29", "2025-07-30"],
        selected_ticker="ALL",
        progress_callback=lambda event: events.append(event),
    )

    assert out["success_count"] == 1
    assert out["failed_count"] == 1
    assert len(events) == 2
    assert events[0]["index"] == 1
    assert events[0]["total"] == 2
    assert events[0]["selected_date"] == "2025-07-29"
    assert events[1]["selected_date"] == "2025-07-30"
    assert "eta_seconds" in events[1]
