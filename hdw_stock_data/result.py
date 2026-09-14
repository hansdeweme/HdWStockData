"""Structured stock retrieval results."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class StockDatasetDescriptor:
    """Describe the actual normalized dataset and its provider."""

    symbol: str
    provider: str
    interval: str
    timezone: str
    currency: str | None
    exchange: str | None
    adjusted: bool
    actual_start: pd.Timestamp
    actual_end: pd.Timestamp
    rows: int


@dataclass(frozen=True)
class StockDataResult:
    """Canonical data, provenance, and optional CSV snapshot location."""

    dataframe: pd.DataFrame
    descriptor: StockDatasetDescriptor
    filepath: Path | None = None
    warnings: tuple[str, ...] = ()

    @property
    def data(self) -> pd.DataFrame:
        """Compatibility alias for dataframe."""
        return self.dataframe
