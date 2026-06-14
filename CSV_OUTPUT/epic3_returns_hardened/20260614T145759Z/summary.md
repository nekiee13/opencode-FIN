# LSTM Backtest Baseline

- Tool version: `1.0.0`  |  torch: `2.6.0+cu124`
- Tickers: AAPL, DJI, GSPC, QQQ, TNX, VIX
- As-of window: 2024-09-23 → 2026-05-07 (step 5), fh=3
- history_mode: `replay`  |  seed: 42

## Overall

- Scored: **1374**  |  Skipped: **84**  |  Skip rate: **5.8%**
- MAE: **84.0101**  |  RMSE: **251.7330**  |  MBE (bias): **-1.3813**
- MedAE: 3.8103  |  MAPE: 2.29%  |  sMAPE: 2.29%
- Directional hit-rate: 49.5%
- Coverage: 86.1% (target 86.0%)  |  mean width: 348.1001

## Per-horizon (the Phase A vs B signal)

| h | N | MAE | RMSE | MBE | dir hit % | coverage % |
|---|---|-----|------|-----|-----------|------------|
| 1 | 474 | 50.2201 | 138.4839 | 1.7485 | 49.9 | 93.7 |
| 2 | 462 | 87.4787 | 273.2789 | -12.5427 | 48.9 | 86.1 |
| 3 | 438 | 116.9186 | 315.0584 | 7.0048 | 49.5 | 77.9 |

## Per-ticker

| ticker | N | MAE | RMSE | MBE | dir hit % | coverage % |
|--------|---|-----|------|-----|-----------|------------|
| AAPL | 229 | 3.7687 | 5.2822 | -0.1240 | 48.2 | 83.0 |
| DJI | 229 | 429.0351 | 610.2053 | -12.5534 | 46.3 | 86.0 |
| GSPC | 229 | 62.3581 | 87.8985 | 3.9832 | 51.5 | 85.2 |
| QQQ | 229 | 7.2833 | 10.3110 | 0.4471 | 52.8 | 86.5 |
| TNX | 229 | 0.0511 | 0.0672 | 0.0030 | 48.0 | 88.2 |
| VIX | 229 | 1.5641 | 2.4963 | -0.0435 | 49.8 | 87.8 |

## Skips by reason

- `error:AssertionError`: 36
- `no_actual`: 48
