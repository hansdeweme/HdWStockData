"""Errors raised by the stock data pipeline."""


class HdWStockDataError(Exception):
    """Base exception for hdw-stock-data."""


class YahooRequestError(HdWStockDataError):
    """Yahoo could not be reached or returned an HTTP error."""


class YahooRateLimitError(YahooRequestError):
    """Yahoo rejected the request because of rate limiting."""


class YahooResponseError(HdWStockDataError):
    """Yahoo returned an unexpected or invalid response."""


class EmptyDatasetError(HdWStockDataError):
    """The provider returned no usable observations."""


class DatasetNormalizationError(HdWStockDataError):
    """Provider data could not be converted to the canonical schema."""


class DatasetValidationError(HdWStockDataError):
    """The normalized dataset violates the market-data contract."""


class SnapshotWriteError(HdWStockDataError):
    """A snapshot could not be written safely."""


class UnsupportedIntervalError(HdWStockDataError):
    """The requested interval has not been validated for this release."""


class UnsupportedLookbackError(HdWStockDataError):
    """The requested lookback exceeds the validated interval capability."""
