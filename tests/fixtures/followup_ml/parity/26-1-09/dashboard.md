# Follow-up ML Board - 26-1-09

- State: `FINAL_TPLUS3`
- Generated at: `2026-02-27 01:15:20`
- Forecast horizon (FH): `3`
- Accuracy/scoring fields: `+3 actual values complete`

## T0 Forecast Matrix (Day 3)

| Ticker | Torch | DYNAMIX | ARIMAX | PCE | LSTM | GARCH | VAR | RW | ETS | Avail | Spread |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| AAPL | 260.5800 | 280.0837 | 264.4966 | 269.9765 | 237.0566 | 274.1719 | 273.9377 | 273.0090 | 273.0090 | 9 | 43.0271 |
| DJI | 49395.1602 | - | - | - | - | - | - | - | - | 1 | 0.0000 |
| QQQ | 603.4700 | 605.9674 | 601.3597 | 607.1155 | 582.8968 | 609.1626 | 607.5304 | 610.0980 | 608.0805 | 9 | 27.2013 |
| SPX | 6861.8901 | - | - | - | - | - | - | - | - | 1 | 0.0000 |
| TNX | 4.0750 | 4.0590 | 4.2445 | 4.0669 | 4.2423 | 4.0288 | - | 4.0269 | 4.0268 | 8 | 0.2176 |
| VIX | 20.2300 | 19.9376 | 15.9899 | 18.1349 | 17.8424 | 20.1809 | 19.6944 | 19.4091 | 19.6078 | 9 | 4.2401 |

## +3 Actuals Ingestion

| Ticker | Expected | Lookup | Actual | Status |
|:--|:--|:--|:--|:--|
| TNX | 2026-02-27 | 2026-02-17 | 4.0520 | ok |
| DJI | 2026-02-27 | 2026-02-17 | 49533.1900 | ok |
| SPX | 2026-02-27 | 2026-02-17 | 6843.2200 | ok |
| VIX | 2026-02-27 | 2026-02-17 | 20.3300 | ok |
| QQQ | 2026-02-27 | 2026-02-17 | 601.3000 | ok |
| AAPL | 2026-02-27 | 2026-02-17 | 263.8800 | ok |

## Partial Scoring

- Coverage: `6/6` tickers with at least one scored model
- Scored rows: `37/54`
- Mean model coverage ratio: `0.685`

| Model | Mean Accuracy | Mean Assign | Scored | Expected | Coverage |
|:--|:--|:--|:--|:--|:--|
| Torch | 99.4629 | 99.1667 | 6 | 6 | 100.0% |
| GARCH | 98.3713 | 97.7500 | 4 | 6 | 66.7% |
| ETS | 97.8099 | 96.7500 | 4 | 6 | 66.7% |
| RW | 97.4821 | 96.7500 | 4 | 6 | 66.7% |
| DYNAMIX | 97.7448 | 96.6875 | 4 | 6 | 66.7% |
| VAR | 97.3419 | 96.0000 | 3 | 6 | 50.0% |
| PCE | 96.3894 | 93.8750 | 4 | 6 | 66.7% |
| ARIMAX | 93.4147 | 91.1875 | 4 | 6 | 66.7% |
| LSTM | 92.4605 | 87.5000 | 4 | 6 | 66.7% |

## AVR Memory (Scaffold)

- History rows: `54`
- Models with history: `9`

| Model | Latest | AVR4 | AVR6 | Rounds | Next Weight |
|:--|:--|:--|:--|:--|:--|
| Torch | 99.1667 | 99.1667 | 99.1667 | 1 | 99.1667 |
| GARCH | 97.7500 | 97.7500 | 97.7500 | 1 | 97.7500 |
| RW | 96.7500 | 96.7500 | 96.7500 | 1 | 96.7500 |
| ETS | 96.7500 | 96.7500 | 96.7500 | 1 | 96.7500 |
| DYNAMIX | 96.6875 | 96.6875 | 96.6875 | 1 | 96.6875 |
| VAR | 96.0000 | 96.0000 | 96.0000 | 1 | 96.0000 |
| PCE | 93.8750 | 93.8750 | 93.8750 | 1 | 93.8750 |
| ARIMAX | 91.1875 | 91.1875 | 91.1875 | 1 | 91.1875 |
| LSTM | 87.5000 | 87.5000 | 87.5000 | 1 | 87.5000 |

## Notes

- This board is generated from persisted round artifacts under out/i_calc.
- Final scoring transformation and AVR feedback are applied in the finalization stage.
