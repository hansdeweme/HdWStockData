"""Public facade for Yahoo stock retrieval and atomic CSV snapshots."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .exceptions import SnapshotWriteError, YahooResponseError
from .normalizer import normalize_yahoo_chart
from .result import StockDataResult, StockDatasetDescriptor
from .yahoo_client import YahooClient, validate_lookback


def _safe_symbol_component(symbol: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "", symbol.lstrip("^")).strip(".-")
    if not value:
        raise ValueError("symbol must contain a usable snapshot filename component")
    return value


def _format_timestamp(value: pd.Timestamp, interval: str) -> str:
    utc = value.tz_convert("UTC")
    if interval in {"1d", "5d", "1wk", "1mo", "3mo"}:
        return utc.strftime("%Y%m%d")
    return utc.strftime("%Y%m%dT%H%M%SZ")


class YahooStockLoader:
    """Retrieve, normalize, describe, and optionally save one stock dataset."""

    def __init__(self, client: YahooClient | None = None) -> None:
        self.client = client if client is not None else YahooClient()

    def load(self, symbol: str, *, interval: str = "1h", days: int = 730,
             preferred_tz: str = "UTC", include_prepost: bool = False,
             save_to: str | Path | None = None) -> StockDataResult:
        """Load observed bars; save_to is a directory for an atomic named CSV.

        Unsupported capabilities raise package errors; other invalid arguments
        raise ValueError before retrieval. Existing snapshots
        with the same generated name are atomically replaced on success.
        """
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a nonempty string")
        symbol = symbol.strip()
        validate_lookback(interval, days)
        if not isinstance(include_prepost, bool):
            raise ValueError("include_prepost must be a boolean")
        if not isinstance(preferred_tz, str) or not preferred_tz:
            raise ValueError("preferred_tz must be a timezone name")
        try:
            target_tz = ZoneInfo(preferred_tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown preferred_tz: {preferred_tz!r}") from exc
        if save_to is not None:
            if not isinstance(save_to, (str, Path)) or not str(save_to).strip() or "\x00" in str(save_to):
                raise ValueError("save_to must be a directory path")
            _safe_symbol_component(symbol)

        raw = self.client.fetch_chart(symbol, interval=interval, days=days,
                                      include_prepost=include_prepost)
        df = normalize_yahoo_chart(raw)
        if preferred_tz != "UTC":
            df = df.tz_convert(target_tz)
        metadata = raw.get("meta", {})
        if not isinstance(metadata, dict):
            raise YahooResponseError("Yahoo chart metadata must be an object.")
        for key in ("currency", "fullExchangeName", "exchangeName"):
            if metadata.get(key) is not None and not isinstance(metadata[key], str):
                raise YahooResponseError(f"Yahoo metadata {key} must be a string.")
        descriptor = StockDatasetDescriptor(
            symbol=symbol, provider="yahoo", interval=interval,
            timezone=str(df.index.tz), currency=metadata.get("currency"),
            exchange=metadata.get("fullExchangeName") or metadata.get("exchangeName"),
            adjusted=False, actual_start=df.index.min(), actual_end=df.index.max(), rows=len(df),
        )
        filepath = None
        if save_to is not None:
            filepath = self._write_snapshot(df, symbol=symbol, interval=interval,
                                            directory=Path(save_to))
        removed = len(raw["timestamp"]) - len(df)
        warnings = ((f"Normalization removed {removed} invalid or duplicate observations.",)
                    if removed else ())
        return StockDataResult(dataframe=df, descriptor=descriptor,
                               filepath=filepath, warnings=warnings)

    def _write_snapshot(self, df: pd.DataFrame, *, symbol: str,
                        interval: str, directory: Path) -> Path:
        """Replace only after a complete write, using a unique same-directory temp file."""
        safe_symbol = _safe_symbol_component(symbol).upper()
        start = _format_timestamp(df.index.min(), interval)
        end = _format_timestamp(df.index.max(), interval)
        final_path = directory / f"{safe_symbol}-yahoo-{interval}-{start}--{end}.csv"
        temporary_path = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                             prefix=f".{final_path.name}.", suffix=".tmp",
                                             dir=directory, delete=False) as stream:
                temporary_path = Path(stream.name)
                df.to_csv(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, final_path)
        except (OSError, ValueError) as exc:
            raise SnapshotWriteError(f"Could not write snapshot {final_path}.") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    # Preserve the original write/replace error if cleanup also fails.
                    pass
        return final_path
