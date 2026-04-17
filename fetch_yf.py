import os
import logging
from time import sleep
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import structlog
import yfinance as yf

# -----------------------------------------------------------------------------
# Logging configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
)

logger = structlog.get_logger()

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
# TICKERS = ["^TNX", "^DJI", "^GSPC", "^VIX", "AAPL", "QQQ"]

START_DATE = "2026-04-10"
END_DATE = "2026-04-15"  # inclusive user end date

OUTPUT_DIR = "./CSV_OUTPUT"
SAVE_INDIVIDUAL_FILES = True
SAVE_COMBINED_FILE = True

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def ensure_output_dir(path: str) -> None:
    """
    Ensure that the output directory exists.
    """
    os.makedirs(path, exist_ok=True)


def inclusive_end_to_exclusive(end_date_str: str) -> str:
    """
    Convert an inclusive end date into an exclusive end date for yfinance.

    yfinance treats the 'end' parameter as exclusive.
    To include 2026-04-01, the request must use 2026-04-02.
    """
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    exclusive_end_dt = end_dt + timedelta(days=1)
    return exclusive_end_dt.strftime("%Y-%m-%d")


def format_date_for_output(date_value) -> str:
    """
    Convert a pandas datetime value to the requested format:
    'Apr 7, 2026'
    """
    dt = pd.to_datetime(date_value)
    return "{month} {day}, {year}".format(
        month=dt.strftime("%b"),
        day=dt.day,
        year=dt.year
    )


def normalize_dataframe_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize downloaded market data to the requested CSV structure.

    Output columns:
    Date,Open,High,Low,Close,Adj Close,Volume
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
        )

    # Force DataFrame copy
    df = pd.DataFrame(df).copy()

    # Flatten MultiIndex columns if returned by yfinance
    if isinstance(df.columns, pd.MultiIndex):
        flattened_columns = []
        for col in df.columns:
            if isinstance(col, tuple):
                flattened_columns.append(col[0])
            else:
                flattened_columns.append(col)
        df.columns = flattened_columns

    df = df.reset_index()

    # Standardize date column name
    if "Date" not in df.columns:
        if "index" in df.columns:
            df = df.rename(columns={"index": "Date"})
        else:
            first_col = df.columns[0]
            df = df.rename(columns={first_col: "Date"})

    # Ensure required columns exist
    required_columns = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]

    for col in required_columns:
        if col not in df.columns:
            if col == "Adj Close":
                if "Close" in df.columns:
                    df[col] = df["Close"]
                else:
                    df[col] = pd.NA
            elif col == "Volume":
                df[col] = 0
            else:
                df[col] = pd.NA

    # Keep only required columns in fixed order
    df = df.loc[:, required_columns].copy()

    # Format date column
    df["Date"] = df["Date"].apply(format_date_for_output)

    # Convert numeric columns
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Volume as integer
    df["Volume"] = df["Volume"].fillna(0).astype("int64")

    # Create temporary sortable date column
    df["_sort_date"] = pd.to_datetime(df["Date"], format="%b %d, %Y")

    # Sort descending by date
    df = df.sort_values("_sort_date", ascending=False).reset_index(drop=True)

    # Drop temporary column
    df = df.drop(columns=["_sort_date"])

    # Force final DataFrame type again for type-checker stability
    df = pd.DataFrame(df)

    return df


def fetch_index_history(
    ticker: str,
    start_date: str,
    end_date_inclusive: str,
    max_retries: int = 3,
    delay_seconds: int = 2,
) -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV data for one ticker using yfinance.

    The end date is converted from inclusive to exclusive because yfinance
    uses an exclusive upper date boundary.
    """
    exclusive_end_date = inclusive_end_to_exclusive(end_date_inclusive)

    for attempt in range(max_retries):
        try:
            logger.info(
                "Downloading historical data",
                ticker=ticker,
                start_date=start_date,
                end_date_inclusive=end_date_inclusive,
                end_date_exclusive=exclusive_end_date,
                attempt=attempt + 1,
            )

            df = yf.download(
                tickers=ticker,
                start=start_date,
                end=exclusive_end_date,
                progress=False,
                auto_adjust=False,
                actions=False,
                threads=False,
            )

            if df is None or df.empty:
                logger.warning(
                    "No historical data returned",
                    ticker=ticker,
                    start_date=start_date,
                    end_date_inclusive=end_date_inclusive,
                )
                return None

            normalized_df = normalize_dataframe_for_csv(pd.DataFrame(df))

            if normalized_df.empty:
                logger.warning(
                    "Normalized data is empty",
                    ticker=ticker,
                )
                return None

            return normalized_df

        except Exception as e:
            logger.error(
                "Download failed",
                ticker=ticker,
                attempt=attempt + 1,
                error=str(e),
            )
            if attempt < max_retries - 1:
                sleep(delay_seconds)
            else:
                return None

    return None


def save_ticker_csv(ticker: str, df: pd.DataFrame, output_dir: str) -> str:
    """
    Save one CSV file per ticker.
    """
    safe_ticker = ticker.replace("^", "")
    file_path = os.path.join(output_dir, "{0}.csv".format(safe_ticker))
    df.to_csv(file_path, index=False, encoding="utf-8")
    logger.info("Saved CSV file", ticker=ticker, path=file_path)
    return file_path


def save_combined_csv(
    data_by_ticker: Dict[str, pd.DataFrame],
    output_dir: str
) -> Optional[str]:
    """
    Save all tickers into one combined CSV file with an added Ticker column.
    """
    combined_frames = []

    for ticker, df in data_by_ticker.items():
        if df is not None and not df.empty:
            temp = pd.DataFrame(df).copy()
            temp.insert(0, "Ticker", ticker)
            combined_frames.append(temp)

    if not combined_frames:
        logger.warning("No data available for combined CSV export")
        return None

    combined_df = pd.concat(combined_frames, ignore_index=True)
    combined_df = pd.DataFrame(combined_df)

    file_path = os.path.join(output_dir, "all_tickers_combined.csv")
    combined_df.to_csv(file_path, index=False, encoding="utf-8")
    logger.info("Saved combined CSV file", path=file_path)
    return file_path


def main() -> None:
    """
    Main entry point.
    """
    ensure_output_dir(OUTPUT_DIR)

    results: Dict[str, pd.DataFrame] = {}

    for ticker in TICKERS:
        df = fetch_index_history(
            ticker=ticker,
            start_date=START_DATE,
            end_date_inclusive=END_DATE,
            max_retries=MAX_RETRIES,
            delay_seconds=RETRY_DELAY_SECONDS,
        )

        if df is not None and not df.empty:
            results[ticker] = df

            if SAVE_INDIVIDUAL_FILES:
                save_ticker_csv(ticker, df, OUTPUT_DIR)
        else:
            logger.warning(
                "Skipping CSV save because no data was retrieved",
                ticker=ticker
            )

    if SAVE_COMBINED_FILE:
        save_combined_csv(results, OUTPUT_DIR)


if __name__ == "__main__":
    main()