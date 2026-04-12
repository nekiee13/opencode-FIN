from __future__ import annotations

import csv

from src.config import paths


REQUIRED_FILES = {
    "TNX": "TNX_data.csv",
    "DJI": "DJI_data.csv",
    "SPX": "GSPC_data.csv",
    "VIX": "VIX_data.csv",
    "QQQ": "QQQ_data.csv",
    "AAPL": "AAPL_data.csv",
}
REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


def test_raw_ticker_csv_headers_and_first_row_are_contract_compatible() -> None:
    tickers_dir = paths.DATA_TICKERS_DIR
    for logical_ticker, file_name in REQUIRED_FILES.items():
        csv_path = tickers_dir / file_name
        assert csv_path.exists(), (
            f"Missing ticker file for {logical_ticker}: {csv_path}"
        )

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames is not None, f"No header in {csv_path}"
            for col in REQUIRED_COLUMNS:
                assert col in reader.fieldnames, f"Missing column {col} in {csv_path}"
            first = next(reader, None)

        assert first is not None, f"No data rows in {csv_path}"
        assert str(first.get("Date") or "").strip(), f"Empty Date in {csv_path}"


def test_raw_ticker_csv_is_adequate_for_fetch_data_loader() -> None:
    from src.data.loading import fetch_data

    for logical_ticker, file_name in REQUIRED_FILES.items():
        csv_path = paths.DATA_TICKERS_DIR / file_name
        df = fetch_data(logical_ticker, csv_path=csv_path)
        assert df is not None, f"fetch_data returned None for {logical_ticker}"
        assert not df.empty, f"fetch_data returned empty data for {logical_ticker}"
        assert type(df.index).__name__ == "DatetimeIndex", (
            f"fetch_data index is not DatetimeIndex for {logical_ticker}"
        )
        assert df.index.is_monotonic_increasing, (
            f"fetch_data index is not sorted for {logical_ticker}"
        )
        assert df.index.is_unique, (
            f"fetch_data index has duplicates for {logical_ticker}"
        )

        for col in ("Open", "High", "Low", "Close"):
            assert col in df.columns, (
                f"Missing normalized column {col} for {logical_ticker}"
            )
            parsed_any = False
            for raw in list(df[col]):
                text = str(raw).strip().replace(",", "")
                if not text:
                    continue
                try:
                    float(text)
                    parsed_any = True
                    break
                except ValueError:
                    continue
            assert parsed_any, (
                f"Column {col} has no numeric values for {logical_ticker}"
            )
