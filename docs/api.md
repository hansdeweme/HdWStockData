# Public API

```python
YahooStockLoader(client=None).load(
    symbol, interval="1h", days=730, preferred_tz="UTC",
    include_prepost=False, save_to=None,
)
```

`save_to` is a directory, not a filename. No snapshot is created by default.
Snapshot filenames use uppercase symbols, retaining only ASCII letters, digits,
dots, underscores, and hyphens, with leading/trailing dots and hyphens removed.
Symbols with no usable filename component are rejected before retrieval when
`save_to` is provided.
Arguments are checked before retrieval, including when a client is injected.
`SUPPORTED_INTERVALS = {"1h"}` and `MAX_LOOKBACK_DAYS = {"1h": 730}` are exported.

`StockDataResult` exposes `dataframe`, `descriptor`, `filepath`, and a tuple of
`warnings` about observations removed by normalization. The descriptor fields
are `symbol`, `provider`, `interval`, `timezone`, `currency`, `exchange`,
`adjusted`, `actual_start`, `actual_end`, and `rows`. Exchange prefers Yahoo's
`fullExchangeName`, falling back to `exchangeName`.

For lower-level use, import `YahooClient` from `hdw_stock_data.yahoo_client`.
It accepts `timeout=15.0`, `max_retries=3` (total attempts), and an optional
`requests.Session`. `fetch_chart()` takes `symbol`, `interval="1h"`, `days=730`,
`include_prepost=False`, and `include_events=False`. Network failures and HTTP
429, 500, 502, 503, and 504 responses are retried; other HTTP errors fail
immediately. Retried HTTP responses use numeric or HTTP-date `Retry-After`,
with exponential backoff as fallback. All retry delays are capped at 30 seconds.
When `days` equals the interval's maximum lookback (730 days for `1h`), the
requested start is moved forward by five minutes to reduce rolling-cutoff
failures from latency or clock skew. Shorter lookbacks are unchanged. This
margin does not guarantee success after unusually long retry delays.

`normalize_yahoo_chart()` and `validate_market_dataframe()` live in
`hdw_stock_data.normalizer`.

All package errors inherit from `HdWStockDataError`: `YahooRequestError`,
`YahooResponseError`, `EmptyDatasetError`, `DatasetNormalizationError`,
`DatasetValidationError`, `SnapshotWriteError`, `UnsupportedIntervalError`,
and `UnsupportedLookbackError`. `YahooRateLimitError` inherits from
`YahooRequestError`. Other invalid caller arguments raise `ValueError`.
The caller chooses whether to log, display, or retry errors.

CSV retains timestamp offsets and instants, not an IANA timezone identifier:

```python
import pandas as pd
frame = pd.read_csv(result.filepath)
frame.index = pd.to_datetime(frame.pop("dt"), utc=True)
frame.index.name = "dt"
frame = frame.tz_convert(result.descriptor.timezone)
frame["number_of_trades"] = frame["number_of_trades"].astype("Float64")
```
