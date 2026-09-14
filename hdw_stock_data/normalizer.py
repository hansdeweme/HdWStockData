"""Convert Yahoo chart observations and validate the market-data contract."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .exceptions import (
    DatasetNormalizationError, DatasetValidationError, EmptyDatasetError,
)

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
OHLCV_COLUMNS = (*REQUIRED_COLUMNS, "number_of_trades")


def normalize_yahoo_chart(result: dict[str, Any]) -> pd.DataFrame:
    """Preserve timestamp instants, allow missing volume, and keep the last duplicate.

    Missing OHLC observations are removed. The nullable trade-count column is
    retained for chart compatibility; Yahoo does not supply trade counts.
    """
    timestamps = result.get("timestamp")
    if timestamps is None or timestamps == []:
        raise EmptyDatasetError("Yahoo returned no timestamps.")

    try:
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise DatasetNormalizationError(
            "Yahoo response is missing quote data."
        ) from exc
    if not isinstance(timestamps, list) or not isinstance(quote, dict):
        raise DatasetNormalizationError("Yahoo timestamps must be an array and quote an object.")
    lengths = {
        column: len(quote[column]) if isinstance(quote.get(column), list) else None
        for column in REQUIRED_COLUMNS
    }
    invalid = {column: length for column, length in lengths.items()
               if length != len(timestamps)}
    if invalid:
        raise DatasetNormalizationError(
            f"Yahoo returned inconsistent column lengths: {invalid}; timestamps={len(timestamps)}."
        )
    try:
        df = pd.DataFrame(
            {column: quote[column] for column in REQUIRED_COLUMNS},
            index=pd.to_datetime(timestamps, unit="s", utc=True),
        )
        df.index.name = "dt"
        for column in REQUIRED_COLUMNS:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DatasetNormalizationError("Could not convert Yahoo observations to the canonical schema.") from exc
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if df.empty:
        raise EmptyDatasetError("No valid OHLC observations remained after normalization.")
    df["number_of_trades"] = pd.Series(pd.NA, index=df.index, dtype="Float64")
    validate_market_dataframe(df)
    return df


def validate_market_dataframe(df: pd.DataFrame) -> None:
    """Validate required OHLCV fields; additional columns are optional."""
    if not isinstance(df, pd.DataFrame):
        raise DatasetValidationError("Dataset must be a pandas DataFrame.")
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise DatasetValidationError(f"Missing required columns: {sorted(missing)}")
    if not df.columns.is_unique:
        raise DatasetValidationError("Dataset contains duplicate columns.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DatasetValidationError("Index must be a pandas DatetimeIndex.")
    if df.index.tz is None:
        raise DatasetValidationError("Datetime index must remain timezone-aware.")
    if df.index.hasnans:
        raise DatasetValidationError("Datetime index contains missing timestamps.")
    if not df.index.is_monotonic_increasing:
        raise DatasetValidationError("Datetime index is not chronologically sorted.")
    if not df.index.is_unique:
        raise DatasetValidationError("Datetime index contains duplicates.")
    for column in REQUIRED_COLUMNS:
        series = df[column]
        if (not pd.api.types.is_numeric_dtype(series.dtype)
                or pd.api.types.is_complex_dtype(series.dtype)
                or pd.api.types.is_bool_dtype(series.dtype)):
            raise DatasetValidationError(f"Column {column!r} must contain real numeric values.")
        if column != "volume" and series.isna().any():
            raise DatasetValidationError("Dataset contains missing OHLC observations.")
        if not np.isfinite(series.dropna()).all():
            raise DatasetValidationError(f"Column {column!r} contains nonfinite values.")
    invalid = (
        (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
        | (df["high"] < df["low"])
    )
    if invalid.any():
        raise DatasetValidationError("Dataset contains invalid OHLC relationships.")
    if (df["volume"].dropna() < 0).any():
        raise DatasetValidationError("Dataset contains negative volume.")
