# Follow-up ML Board - 26-1-06

- State: `FINAL_TPLUS3`
- Generated at: `2026-02-28 18:40:13`
- Forecast horizon (FH): `3`
- Run mode: `lookup_override_test`
- Override notice: `lookup_date=2026-02-10` (backtest/evaluation mode, not strict production)
- Accuracy/scoring fields: `+3 actual values complete`

## T0 Forecast Matrix (Day 3)

| Ticker | Torch | DYNAMIX | ARIMAX | PCE | LSTM | GARCH | VAR | RW | ETS | Avail | Spread |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| AAPL | 260.5800 | 281.2593 | 264.4966 | 269.9765 | 237.0566 | 274.1719 | 273.9377 | 273.0090 | 273.0090 | 9 | 44.2027 |
| DJI | 49395.1602 | 49146.2969 | 49482.2698 | 49586.6772 | 5812.3826 | 49239.4527 | 49263.7192 | 49314.9264 | 49283.4486 | 9 | 43774.2946 |
| QQQ | 603.4700 | 603.6251 | 601.3597 | 607.1155 | 582.8968 | 609.1626 | 607.5304 | 610.0980 | 608.0805 | 9 | 27.2013 |
| SPX | 6861.8901 | 6845.0215 | 6824.4168 | 6870.3135 | 5478.8816 | 6888.8129 | 6890.7587 | 6911.7912 | 6909.2240 | 9 | 1432.9096 |
| TNX | 4.0750 | 4.1276 | 4.2445 | 4.0669 | 4.2423 | 4.0288 | - | 4.0269 | 4.0268 | 8 | 0.2176 |
| VIX | 20.2300 | 19.1781 | 15.9899 | 18.1349 | 17.8424 | 20.1809 | 19.6944 | 19.4091 | 19.6078 | 9 | 4.2401 |

## +3 Actuals Ingestion

| Ticker | Expected | Lookup | Actual | Status |
|:--|:--|:--|:--|:--|
| TNX | 2026-02-27 | 2026-02-10 | 4.1470 | ok |
| DJI | 2026-02-27 | 2026-02-10 | 50188.1400 | ok |
| SPX | 2026-02-27 | 2026-02-10 | 6941.8100 | ok |
| VIX | 2026-02-27 | 2026-02-10 | 17.7900 | ok |
| QQQ | 2026-02-27 | 2026-02-10 | 611.4700 | ok |
| AAPL | 2026-02-27 | 2026-02-10 | 273.6800 | ok |

## Partial Scoring

- Coverage: `6/6` tickers with at least one scored model
- Scored rows: `53/54`
- Mean model coverage ratio: `0.981`

| Model | Mean Accuracy | Mean Assign | Scored | Expected | Coverage |
|:--|:--|:--|:--|:--|:--|
| PCE | 98.6393 | 98.1667 | 6 | 6 | 100.0% |
| RW | 97.5603 | 97.3333 | 6 | 6 | 100.0% |
| DYNAMIX | 97.3678 | 96.5833 | 6 | 6 | 100.0% |
| ETS | 97.3022 | 95.5417 | 6 | 6 | 100.0% |
| GARCH | 96.7498 | 95.5417 | 6 | 6 | 100.0% |
| VAR | 97.1959 | 95.1800 | 5 | 6 | 83.3% |
| Torch | 95.9537 | 94.5000 | 6 | 6 | 100.0% |
| ARIMAX | 96.5709 | 94.3333 | 6 | 6 | 100.0% |
| LSTM | 78.3100 | 73.5833 | 6 | 6 | 100.0% |

## AVR Memory (Scaffold)

- History rows: `162`
- Models with history: `9`

| Model | Latest | AVR4 | AVR6 | Rounds | Next Weight |
|:--|:--|:--|:--|:--|:--|
| Torch | 99.1667 | 97.6111 | 97.6111 | 3 | 97.6111 |
| RW | 97.4167 | 97.1667 | 97.1667 | 3 | 97.1667 |
| GARCH | 98.1667 | 97.1528 | 97.1528 | 3 | 97.1528 |
| DYNAMIX | 97.2500 | 96.8403 | 96.8403 | 3 | 96.8403 |
| ETS | 97.5000 | 96.5972 | 96.5972 | 3 | 96.5972 |
| VAR | 97.2000 | 96.1267 | 96.1267 | 3 | 96.1267 |
| PCE | 95.7917 | 95.9444 | 95.9444 | 3 | 95.9444 |
| ARIMAX | 94.0000 | 93.1736 | 93.1736 | 3 | 93.1736 |
| LSTM | 71.6667 | 77.5833 | 77.5833 | 3 | 77.5833 |

## Notes

- This board is generated from persisted round artifacts under out/i_calc.
- Final scoring transformation and AVR feedback are applied in the finalization stage.
