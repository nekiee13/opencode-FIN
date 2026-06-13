# LSTM Backtest Baseline

- Tool version: `1.0.0`  |  torch: `2.6.0+cu124`
- Tickers: AAPL, DJI, GSPC, QQQ, TNX, VIX
- As-of window: 2024-09-23 → 2026-05-07 (step 5), fh=3
- history_mode: `replay`  |  seed: 42

## Overall

- Scored: **1374**  |  Skipped: **84**  |  Skip rate: **5.8%**
- MAE: **298.9376**  |  RMSE: **788.8184**  |  MBE (bias): **-211.9426**
- MedAE: 12.5234  |  MAPE: 5.12%  |  sMAPE: 5.30%
- Directional hit-rate: 50.4%
- Coverage: 55.2% (target 86.0%)  |  mean width: 537.0378

## Per-horizon (the Phase A vs B signal)

| h | N | MAE | RMSE | MBE | dir hit % | coverage % |
|---|---|-----|------|-----|-----------|------------|
| 1 | 474 | 282.8513 | 766.1858 | -201.8375 | 48.8 | 59.5 |
| 2 | 462 | 299.8214 | 788.0636 | -230.8406 | 53.9 | 55.4 |
| 3 | 438 | 315.4138 | 813.3734 | -202.9447 | 48.4 | 50.5 |

## Per-ticker

| ticker | N | MAE | RMSE | MBE | dir hit % | coverage % |
|--------|---|-----|------|-----|-----------|------------|
| AAPL | 229 | 11.4695 | 15.6049 | -6.0207 | 48.7 | 59.4 |
| DJI | 229 | 1500.5247 | 1905.9504 | -1040.0208 | 48.5 | 52.0 |
| GSPC | 229 | 254.1107 | 315.5178 | -204.8242 | 48.9 | 39.7 |
| QQQ | 229 | 24.9783 | 30.7838 | -19.9195 | 47.2 | 52.4 |
| TNX | 229 | 0.1314 | 0.1695 | -0.0845 | 49.8 | 62.9 |
| VIX | 229 | 2.4109 | 4.1193 | -0.7857 | 59.4 | 65.1 |

## Skips by reason

- `error:AssertionError`: 36
- `no_actual`: 48
