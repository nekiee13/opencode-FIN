# Pydantic Model Specification (Dataclass-Aligned)

This specification maps current FIN dataclass entities to Pydantic models for validation, serialization, and API boundary stability.

Notes:
- Existing runtime entities are dataclasses; this document defines equivalent Pydantic contracts.
- `pandas.DataFrame` and `pandas.Timestamp` fields are represented as JSON-safe wrappers at API boundaries.
- Validation is strict by default (`extra = "forbid"`) for external payloads.

## Mapping: Dataclass -> Pydantic Model

| Dataclass Entity | Pydantic Model Name | Source |
|---|---|---|
| `ForecastArtifact` | `ForecastArtifactModel` | `src/models/facade.py` |
| `ForecastBundle` | `ForecastBundleModel` | `src/models/facade.py` |
| `ARIMAXResult` | `ARIMAXResultModel` | `src/models/arimax.py` |
| `LSTMResult` | `LSTMResultModel` | `src/models/lstm.py` |
| `PCENARXResult` | `PCENARXResultModel` | `src/models/pce_narx.py` |
| `DynaMixResult` | `DynaMixResultModel` | `src/models/dynamix.py` |
| `ETSResult` | `ETSResultModel` | `src/models/ets.py` |
| `GARCHResult` | `GARCHResultModel` | `src/models/garch.py` |
| `VARResult` | `VARResultModel` | `src/models/var.py` |
| `RandomWalkResult` | `RandomWalkResultModel` | `src/models/random_walk.py` |
| `PISettings` | `PISettingsModel` | `src/models/intervals.py` |
| `ExoSpec` | `ExoSpecModel` | `src/exo/exo_config.py` |
| `ValidationParams` | `ValidationParamsModel` | `src/exo/exo_validator.py` |
| `WilliamsSignal` | `WilliamsSignalModel` | `src/structural/svl_indicators.py` |
| `HurstPack` | `HurstPackModel` | `src/structural/svl_indicators.py` |
| `TickerStructuralContext` | `TickerStructuralContextModel` | `src/structural/svl_indicators.py` |
| `TickerTDAContext` | `TickerTDAContextModel` | `src/structural/tda_indicators.py` |
| `PivotCalcResult` | `PivotCalcResultModel` | `src/utils/pivots.py` |
| `_Defaults` | `GuiDefaultsModel` | `src/ui/gui.py` |
| `DraftArtifacts` | `DraftArtifactsModel` | `src/followup_ml/draft.py` |
| `FinalizeArtifacts` | `FinalizeArtifactsModel` | `src/followup_ml/draft.py` |
| `PullRequestRef` | `PullRequestRefModel` | `src/followup_ml/scope_audit.py` |
| `ScopeAuditResult` | `ScopeAuditResultModel` | `src/followup_ml/scope_audit.py` |
| `TDAModule` | `TDAModuleModel` (metadata-only) | `scripts/tda_export.py` |
| `ExportPaths` | `ExportPathsModel` | `scripts/tda_export.py` |
| `WorkerInput` | `PCEWorkerInputModel` | `scripts/workers/pce_worker.py` |

## Canonical Model Definitions (Reference)

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DataFramePayload(StrictModel):
    """
    JSON-safe dataframe wrapper for API boundaries.
    columns: ordered column names
    index: ISO datetime strings when time-indexed
    rows: list of row records
    """

    columns: List[str]
    index: List[str]
    rows: List[Dict[str, Any]]


class ForecastArtifactModel(StrictModel):
    pred_df: DataFramePayload
    pred_col: str
    model: str = "UNKNOWN"
    lower_col: Optional[str] = None
    upper_col: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ForecastBundleModel(StrictModel):
    ticker: str
    fh: int = Field(ge=1)
    forecasts: Dict[str, ForecastArtifactModel]
    warnings: List[str] = Field(default_factory=list)


class PISettingsModel(StrictModel):
    coverage: float = Field(gt=0.0, lt=1.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    q_low: float = Field(ge=0.0, le=1.0)
    q_high: float = Field(ge=0.0, le=1.0)
    z_two_sided: float = Field(gt=0.0)
    calibration_enabled: bool
    calibration_min_samples: int = Field(ge=1)


class BaseModelResult(StrictModel):
    model_used: str
    cols_used: List[str]
    pred_df: DataFramePayload
    pred_col: Optional[str] = None
    lower_col: Optional[str] = None
    upper_col: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ARIMAXResultModel(BaseModelResult):
    model_order: Optional[Tuple[int, int, int]] = None
    residuals: Optional[List[float]] = None


class LSTMResultModel(BaseModelResult):
    pred_col: str = "LSTM_Pred"
    lower_col: str = "LSTM_Lower"
    upper_col: str = "LSTM_Upper"


class PCENARXResultModel(BaseModelResult):
    pred_col: str = "PCE_Pred"
    lower_col: str = "PCE_Lower"
    upper_col: str = "PCE_Upper"


class DynaMixResultModel(BaseModelResult):
    pred_col: str = "DYNAMIX_Pred"
    lower_col: str = "DYNAMIX_Lower"
    upper_col: str = "DYNAMIX_Upper"


class ETSResultModel(BaseModelResult):
    pass


class GARCHResultModel(BaseModelResult):
    pred_col: str = "GARCH_Pred"
    lower_col: str = "GARCH_Lower"
    upper_col: str = "GARCH_Upper"


class VARResultModel(BaseModelResult):
    pred_col: str = "VAR_Pred"
    lower_col: str = "VAR_Lower"
    upper_col: str = "VAR_Upper"


class RandomWalkResultModel(BaseModelResult):
    pred_col: str = "RW_Pred"
    lower_col: str = "RW_Lower"
    upper_col: str = "RW_Upper"


class ExoSpecModel(StrictModel):
    enabled: bool
    scenario_mode: str
    values: List[Optional[float]]

    @field_validator("scenario_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        vv = str(v).upper().strip()
        allowed = {"NONE", "DELTA", "ABS"}
        if vv not in allowed:
            raise ValueError(f"scenario_mode must be one of {sorted(allowed)}")
        return vv


class ValidationParamsModel(StrictModel):
    window: int = Field(ge=2)
    jump_sigma_mult: float = Field(gt=0.0)
    drift_sigma_mult: float = Field(gt=0.0)
    quantile_lo: float = Field(ge=0.0, le=1.0)
    quantile_hi: float = Field(ge=0.0, le=1.0)
    min_points: int = Field(ge=2)
    eps: float = Field(gt=0.0)


class WilliamsSignalModel(StrictModel):
    signal_last5: str
    level: Optional[float] = None
    note: str = ""


class HurstPackModel(StrictModel):
    h20_current: Optional[float] = None
    h60_current: Optional[float] = None
    h120_current: Optional[float] = None
    regime_current: str
    h20_last10: List[Optional[float]]
    regime_change_last10: str
    regime_change_note: str


class TickerStructuralContextModel(StrictModel):
    ticker: str
    asof_date: str
    hurst: HurstPackModel
    trend10d: str
    williams: WilliamsSignalModel
    provenance: Dict[str, str]


class TickerTDAContextModel(StrictModel):
    ticker: str
    asof: datetime
    window_len: int = Field(ge=1)
    embed_m: int = Field(ge=1)
    embed_tau: int = Field(ge=1)
    persist_thr: float = Field(ge=0.0)
    lastn: int = Field(ge=1)
    state: str
    n_obs: int = Field(ge=0)
    n_embed: int = Field(ge=0)
    ret_vol: Optional[float] = None
    h0_max_persist: Optional[float] = None
    h1_max_persist: Optional[float] = None
    h1_sum_persist: Optional[float] = None
    h1_entropy_proxy: Optional[float] = None
    h1_count_above_thr: Optional[float] = None
    h1_entropy: Optional[float] = None
    h1_label: str = "UNKNOWN"
    cycle_note: str = ""
    provenance: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PivotCalcResultModel(StrictModel):
    pivot_data: Dict[str, Dict[str, float]]
    asof_date: datetime
    based_on_date: datetime


class GuiDefaultsModel(StrictModel):
    APP_VERSION: str = "0.0"
    TICKERS: Tuple[str, ...]
    SHOW_PEAKS_TROUGHS: bool = True
    SHOW_REGIMES: bool = False
    HISTORY_PERIODS: Tuple[str, ...]


class DraftArtifactsModel(StrictModel):
    round_id: str
    round_dir: Path
    forecasts_csv: Path
    draft_metrics_csv: Path
    day3_matrix_csv: Path
    weighted_ensemble_csv: Path
    context_json: Path
    dashboard_md: Path


class FinalizeArtifactsModel(StrictModel):
    round_id: str
    round_state: str
    run_mode: str
    lookup_date_override: str
    ok_actuals: int
    total_actuals: int
    scored_rows: int
    mapped_rows: int
    total_score_rows: int
    model_coverage_avg: float
    actuals_csv: Path
    partial_scores_csv: Path
    model_summary_csv: Path
    avr_history_csv: Path
    avr_summary_csv: Path
    next_weights_csv: Path
    context_json: Path
    dashboard_md: Path


class PullRequestRefModel(StrictModel):
    number: int = Field(ge=1)
    title: str
    url: str
    merged_at: str


class ScopeAuditResultModel(StrictModel):
    repo: str
    since: str
    generated_at: str
    total_merged_prs: int = Field(ge=0)
    exception_merges_count: int = Field(ge=0)
    missing_scope_label_merges_count: int = Field(ge=0)
    violations_count: int = Field(ge=0)
    exception_prs: Tuple[PullRequestRefModel, ...] = ()
    missing_scope_label_prs: Tuple[PullRequestRefModel, ...] = ()


class TDAModuleModel(StrictModel):
    # Metadata shape only; callables are runtime objects not serialized.
    DEFAULT_WINDOW_LEN: int = 60
    DEFAULT_EMBED_M: int = 3
    DEFAULT_EMBED_TAU: int = 1
    DEFAULT_PERSIST_THR: float = 0.5
    DEFAULT_LASTN: int = 10


class ExportPathsModel(StrictModel):
    context_md: Path
    metrics_csv: Optional[Path] = None
    prompt_header: Optional[Path] = None


class PCEWorkerInputModel(StrictModel):
    enriched_data_csv: str
    exog_train_csv: Optional[str] = None
    exog_future_csv: Optional[str] = None
    ticker: str = ""
    target_col: Optional[str] = None
    fh: Optional[int] = Field(default=None, ge=1)
    forecast_csv_out: str
```

## Boundary Conversion Policy

- Internal runtime can keep dataclasses for low-overhead domain objects.
- External boundaries (CLI payloads, worker IPC, persisted JSON, API responses) should validate with Pydantic models.
- For dataframe-rich entities, use deterministic conversion helpers:
  - DataFrame -> `DataFramePayload`
  - `DataFramePayload` -> DataFrame

## Example: ForecastArtifact JSON Payload

```json
{
  "pred_df": {
    "columns": ["ARIMAX_Pred", "ARIMAX_Lower", "ARIMAX_Upper"],
    "index": ["2026-03-27", "2026-03-30", "2026-03-31"],
    "rows": [
      {"ARIMAX_Pred": 510.2, "ARIMAX_Lower": 503.1, "ARIMAX_Upper": 517.3},
      {"ARIMAX_Pred": 511.0, "ARIMAX_Lower": 503.0, "ARIMAX_Upper": 518.9},
      {"ARIMAX_Pred": 512.4, "ARIMAX_Lower": 503.7, "ARIMAX_Upper": 520.8}
    ]
  },
  "pred_col": "ARIMAX_Pred",
  "model": "ARIMAX",
  "lower_col": "ARIMAX_Lower",
  "upper_col": "ARIMAX_Upper",
  "meta": {
    "ticker": "AAPL",
    "fh": 3
  }
}
```
