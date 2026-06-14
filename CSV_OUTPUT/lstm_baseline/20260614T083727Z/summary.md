# LSTM Backtest Baseline

- Tool version: `1.0.0`  |  torch: `2.6.0+cu124`
- Tickers: AAPL, DJI, GSPC, QQQ, TNX, VIX
- As-of window: 2024-09-23 → 2026-05-07 (step 5), fh=3
- history_mode: `replay`  |  seed: 42

## Overall

- Scored: **1374**  |  Skipped: **84**  |  Skip rate: **5.8%**
- MAE: **130.8979**  |  RMSE: **359.4416**  |  MBE (bias): **-10.2194**
- MedAE: 7.6153  |  MAPE: 3.56%  |  sMAPE: 3.60%
- Directional hit-rate: 50.3%
- Coverage: 55.5% (target 86.0%)  |  mean width: 337.0721

## Per-horizon (the Phase A vs B signal)

| h | N | MAE | RMSE | MBE | dir hit % | coverage % |
|---|---|-----|------|-----|-----------|------------|
| 1 | 474 | 117.0984 | 341.1823 | -2.3574 | 47.8 | 62.4 |
| 2 | 462 | 125.8373 | 342.4063 | -24.2336 | 55.2 | 55.8 |
| 3 | 438 | 151.1694 | 394.5300 | -3.9454 | 47.7 | 47.5 |

## Per-ticker

| ticker | N | MAE | RMSE | MBE | dir hit % | coverage % |
|--------|---|-----|------|-----|-----------|------------|
| AAPL | 229 | 7.1235 | 9.6567 | -0.9390 | 46.9 | 52.0 |
| DJI | 229 | 645.2995 | 866.4700 | -32.7407 | 55.0 | 58.1 |
| GSPC | 229 | 116.4495 | 154.7782 | -23.7469 | 51.5 | 61.6 |
| QQQ | 229 | 14.1334 | 18.8135 | -3.3909 | 48.9 | 58.5 |
| TNX | 229 | 0.0686 | 0.0905 | -0.0127 | 48.0 | 55.5 |
| VIX | 229 | 2.3126 | 3.9743 | -0.4858 | 51.1 | 47.2 |

## Skips by reason

- `error:AssertionError`: 36
- `no_actual`: 48
