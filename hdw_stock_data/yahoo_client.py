"""Retrieve validated Yahoo chart JSON through an injectable HTTP session."""

from __future__ import annotations
import math
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
import requests
# local imports
from .exceptions import (YahooRateLimitError, YahooRequestError, YahooResponseError,
                         UnsupportedIntervalError, UnsupportedLookbackError)
from .version import VERSION

DEFAULT_USER_AGENT = f"hdw-stock-data/{VERSION}"
MAX_LOOKBACK_DAYS = {"1h": 730}
SUPPORTED_INTERVALS = {"1h"}
MAX_RETRY_DELAY = 30.0
_RETRYABLE_SERVER_STATUSES = {500, 502, 503, 504}
_LOOKBACK_BOUNDARY_MARGIN = timedelta(minutes=5)


def validate_lookback(interval: str, days: int) -> None:
    """Enforce this release's tested capabilities, not guaranteed data coverage."""
    if not isinstance(interval, str) or interval not in SUPPORTED_INTERVALS:
        raise UnsupportedIntervalError(f"Interval {interval!r} has not been validated.")
    maximum = MAX_LOOKBACK_DAYS.get(interval)
    if maximum is None:
        raise UnsupportedIntervalError(f"Interval {interval!r} has not been validated.")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError("days must be a positive integer")
    if days > maximum:
        raise UnsupportedLookbackError(
            f"Yahoo currently supports at most {maximum} days "
            f"for interval {interval!r}; requested {days}."
        )


def validate_response(result: dict[str, Any]) -> None:
    """Validate the chart structure without converting observations."""
    if not isinstance(result, dict):
        raise YahooResponseError("Yahoo chart result must be an object.")
    if not isinstance(result.get("meta", {}), dict):
        raise YahooResponseError("Yahoo chart metadata must be an object.")
    for field in ("currency", "exchangeName", "exchangeTimezoneName"):
        value = result.get("meta", {}).get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise YahooResponseError(f"Yahoo metadata {field} must be a nonempty string.")
    timestamps = result.get("timestamp")
    # Yahoo can omit observations for an empty range. Normalization handles it.
    if timestamps is None or timestamps == []:
        return
    if not isinstance(timestamps, list):
        raise YahooResponseError("Yahoo timestamps must be an array.")
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    if not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], dict):
        raise YahooResponseError("Yahoo response must contain one quote object.")
    for column in ("open", "high", "low", "close", "volume"):
        values = quotes[0].get(column)
        if not isinstance(values, list) or len(values) != len(timestamps):
            raise YahooResponseError(f"Yahoo {column} must match the timestamp array length.")


class YahooClient:
    """Request Yahoo chart observations; max_retries is the total attempt limit."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self, *, timeout: float = 15.0, max_retries: int = 3,
                 session: requests.Session | None = None) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session if session is not None else requests.Session()
        if session is None:
            self.session.headers["User-Agent"] = DEFAULT_USER_AGENT
        else:
            self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

    def fetch_chart(self, symbol: str, *, interval: str = "1h", days: int = 730,
                    include_prepost: bool = False,
                    include_events: bool = False) -> dict[str, Any]:
        """Fetch a rolling UTC range ending now, returning the chart result."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a nonempty string")
        validate_lookback(interval, days)
        if not isinstance(include_prepost, bool) or not isinstance(include_events, bool):
            raise ValueError("include_prepost and include_events must be booleans")
        now = datetime.now(timezone.utc)
        try:
            start = now - timedelta(days=days)
        except OverflowError as exc:
            raise ValueError("days is outside the supported datetime range") from exc
        if days == MAX_LOOKBACK_DAYS[interval]:
            # Stay inside Yahoo's rolling cutoff despite latency or clock skew.
            start += _LOOKBACK_BOUNDARY_MARGIN
        symbol = symbol.strip()
        url = f"{self.BASE_URL}/{quote(symbol, safe='')}"
        params = {
            "period1": int(start.timestamp()), "period2": int(now.timestamp()),
            "interval": interval, "includePrePost": str(include_prepost).lower(),
            "events": "div,splits" if include_events else "",
        }
        response = self._request(url, params=params)
        try:
            return self._decode_payload(response, symbol)
        finally:
            response.close()

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        """Use Retry-After or exponential backoff, capped at 30 seconds."""
        if value:
            try:
                delay = float(value)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    delay = float("nan")
            if math.isfinite(delay) and delay >= 0:
                return min(delay, MAX_RETRY_DELAY)
        return min(2 ** min(attempt, 5), MAX_RETRY_DELAY)

    def _request(self, url: str, *, params: dict[str, object]) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == self.max_retries - 1:
                    raise YahooRequestError("Yahoo Finance request failed.") from exc
                time.sleep(self._retry_delay(None, attempt))
                continue
            if response.status_code == 429:
                delay = self._retry_delay(response.headers.get("Retry-After"), attempt)
                response.close()
                if attempt == self.max_retries - 1:
                    raise YahooRateLimitError("Yahoo Finance rate limit exceeded.")
                time.sleep(delay)
                continue
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                response.close()
                if (response.status_code in _RETRYABLE_SERVER_STATUSES
                        and attempt < self.max_retries - 1):
                    time.sleep(self._retry_delay(response.headers.get("Retry-After"), attempt))
                    continue
                raise YahooRequestError(f"Yahoo returned HTTP {response.status_code}.") from exc
            return response
        raise YahooRequestError("Yahoo request failed unexpectedly.")

    @staticmethod
    def _decode_payload(response: requests.Response, symbol: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise YahooResponseError("Yahoo returned invalid JSON.") from exc
        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            raise YahooResponseError("Yahoo response does not contain a chart object.")
        if chart.get("error"):
            raise YahooResponseError(f"Yahoo rejected symbol {symbol!r}: {chart['error']}")
        results = chart.get("result")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise YahooResponseError(f"Yahoo returned no valid single result for {symbol!r}.")
        validate_response(results[0])
        return results[0]
