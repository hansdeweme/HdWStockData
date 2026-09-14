"""Yahoo OHLCV data compatible with hdw_crypto_data's analysis frames.

Use YahooStockLoader().load("AAPL", days=730).dataframe for a UTC-indexed frame.
"""

from .exceptions import (YahooResponseError, EmptyDatasetError, SnapshotWriteError,
                         HdWStockDataError, YahooRequestError, YahooRateLimitError,
                         DatasetNormalizationError, DatasetValidationError,
                         UnsupportedIntervalError, UnsupportedLookbackError)
from .yahoo_client import MAX_LOOKBACK_DAYS, SUPPORTED_INTERVALS
from .loader import YahooStockLoader
from .result import StockDataResult, StockDatasetDescriptor
from .version import VERSION as __version__

__all__ = [
    "DatasetNormalizationError",
    "DatasetValidationError",
    "EmptyDatasetError",
    "HdWStockDataError",
    "SnapshotWriteError",
    "UnsupportedIntervalError",
    "UnsupportedLookbackError",
    "MAX_LOOKBACK_DAYS",
    "SUPPORTED_INTERVALS",
    "StockDataResult",
    "StockDatasetDescriptor",
    "YahooRateLimitError",
    "YahooRequestError",
    "YahooResponseError",
    "YahooStockLoader",
    "__version__",
]
