# HdW Stock Data

`hdw-stock-data` 0.1.0: retrieve stock observations directly
from Yahoo's chart HTTP endpoint, normalize OHLCV, preserve timestamp instants,
and optionally write an atomic CSV snapshot. It uses `requests`, not yfinance.
This project is independent of `hdw-crypto-data`.

## Install

Python 3.11 or newer is required. Install from PyPI:

```powershell
python -m pip install hdw-stock-data
```

For development, run from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Use

```python
from hdw_stock_data import YahooStockLoader

result = YahooStockLoader().load(
    "^GSPC", interval="1h", days=730,
    preferred_tz="Europe/Amsterdam", save_to="snapshots",
)
sp500 = result.dataframe["close"].rename("sp500")
print(result.descriptor)
print(result.filepath, result.warnings)
```

Only `1h` is validated for this release. Both client and loader default to
730 days and reject longer ranges before retrieval. This is a tested capability
limit, not a guarantee that every symbol has 730 days of observations.
At the 730-day limit, the client moves the requested start forward by five
minutes to provide a margin inside Yahoo's rolling cutoff. Shorter requests
retain their full duration.

## Data contract

The frame has a sorted, unique, timezone-aware `DatetimeIndex` named `dt` and
numeric `open`, `high`, `low`, `close`, `volume` columns. Missing OHLC rows are
removed; missing volume is retained. The last valid duplicate is kept. Invalid
OHLC relationships, negative volume, nonfinite values, and invalid timestamps
are rejected. No shifts, resampling, or gap filling are applied.

`number_of_trades` contains `pd.NA` with nullable `Float64` dtype for chart
compatibility. Trade counts are unavailable, not zero. This additional column
is optional to the market-data validator. `result.data` aliases `dataframe`.

The descriptor records actual normalized bounds and count, currency and exchange
when available, provider `yahoo`, and output timezone. `adjusted=False` means
the package performs no price adjustment; source adjustments are not undone.

## Verification

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.13 -m build
py -3.13 -m twine check dist/*
```

Tests use mocked HTTP responses and local files. Live requests are opt-in:

```powershell
py -3.13 -m examples.fetch_stock AAPL --days 5
```

Run the initial stock and index smoke test (`AAPL`, `ASML.AS`, `^GSPC`, `^VIX`):

```powershell
py -3.13 -m examples.test_assets
py -3.13 -m examples.test_assets --days 5 --save-to snapshots
```

This retrieves hourly bars, prints actual bounds and the latest five rows for
each symbol, and exits with status 1 if any retrieval fails. The default output
timezone is `Europe/Amsterdam`; override it with `--timezone UTC`. You can also
provide a different list of symbols as positional arguments.

See [architecture](docs/architecture.md), [API](docs/api.md), and
[testing plan](docs/testing.md), and [showcase setup](docs/showcase.md). No live-provider coverage is claimed by the
offline test suite.
