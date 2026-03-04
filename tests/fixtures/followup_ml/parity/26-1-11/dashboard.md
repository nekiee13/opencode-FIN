# Follow-up ML Board - 26-1-11

- State: `FINAL_TPLUS3`
- Generated at: `2026-02-28 10:39:57`
- Forecast horizon (FH): `3`
- Accuracy/scoring fields: `+3 actual values complete`

## T0 Forecast Matrix (Day 3)

| Ticker | Torch | DYNAMIX | ARIMAX | PCE | LSTM | GARCH | VAR | RW | ETS | Avail | Spread |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| AAPL | 260.5800 | 281.2565 | 264.4966 | 269.9765 | 237.0566 | 274.1719 | 273.9377 | 273.0090 | 273.0090 | 9 | 44.1999 |
| DJI | 49395.1602 | 48933.7344 | 49482.2698 | 49586.6772 | 5812.3826 | 49239.4527 | 49263.7192 | 49314.9264 | 49283.4486 | 9 | 43774.2946 |
| QQQ | 603.4700 | 605.1278 | 601.3597 | 607.1155 | 582.8968 | 609.1626 | 607.5304 | 610.0980 | 608.0805 | 9 | 27.2013 |
| SPX | 6861.8901 | 6865.3242 | 6824.4168 | 6870.3135 | 5478.8816 | 6888.8129 | 6890.7587 | 6911.7912 | 6909.2240 | 9 | 1432.9096 |
| TNX | 4.0750 | 4.0830 | 4.2445 | 4.0669 | 4.2423 | 4.0288 | - | 4.0269 | 4.0268 | 8 | 0.2176 |
| VIX | 20.2300 | 20.0918 | 15.9899 | 18.1349 | 17.8424 | 20.1809 | 19.6944 | 19.4091 | 19.6078 | 9 | 4.2401 |

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
- Scored rows: `53/54`
- Mean model coverage ratio: `0.981`

| Model | Mean Accuracy | Mean Assign | Scored | Expected | Coverage |
|:--|:--|:--|:--|:--|:--|
| Torch | 99.4629 | 99.1667 | 6 | 6 | 100.0% |
| GARCH | 98.7043 | 98.1667 | 6 | 6 | 100.0% |
| ETS | 98.2951 | 97.5000 | 6 | 6 | 100.0% |
| RW | 98.0810 | 97.4167 | 6 | 6 | 100.0% |
| DYNAMIX | 98.2182 | 97.2500 | 6 | 6 | 100.0% |
| VAR | 98.1574 | 97.2000 | 5 | 6 | 83.3% |
| PCE | 97.5090 | 95.7917 | 6 | 6 | 100.0% |
| ARIMAX | 95.5469 | 94.0000 | 6 | 6 | 100.0% |
| LSTM | 76.9398 | 71.6667 | 6 | 6 | 100.0% |

## AVR Memory (Scaffold)

- History rows: `108`
- Models with history: `9`

| Model | Latest | AVR4 | AVR6 | Rounds | Next Weight |
|:--|:--|:--|:--|:--|:--|
| Torch | 99.1667 | 99.1667 | 99.1667 | 2 | 99.1667 |
| GARCH | 98.1667 | 97.9583 | 97.9583 | 2 | 97.9583 |
| ETS | 97.5000 | 97.1250 | 97.1250 | 2 | 97.1250 |
| RW | 97.4167 | 97.0833 | 97.0833 | 2 | 97.0833 |
| DYNAMIX | 97.2500 | 96.9688 | 96.9688 | 2 | 96.9688 |
| VAR | 97.2000 | 96.6000 | 96.6000 | 2 | 96.6000 |
| PCE | 95.7917 | 94.8333 | 94.8333 | 2 | 94.8333 |
| ARIMAX | 94.0000 | 92.5938 | 92.5938 | 2 | 92.5938 |
| LSTM | 71.6667 | 79.5833 | 79.5833 | 2 | 79.5833 |

## Notes

- This board is generated from persisted round artifacts under out/i_calc.
- Final scoring transformation and AVR feedback are applied in the finalization stage.
