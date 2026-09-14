# Shared market showcase

Run from this checkout with `py -3.13 showcase_pyqt_app.py`.
The GUI needs PyQt6. Charting also needs the dependencies imported by the local
`ta_charts.py`: numpy, pandas, pandas_ta, plotly, ta, scipy, and progressbar2.
The crypto package is imported only when a crypto request runs. The local
`stylesheet.py` supplies the original showcase's dark theme.

At startup, the showcase checks whether `hdw_stock_data` and `hdw_crypto_data`
are available in the current Python environment (including source checkouts).
If either is missing, a persistent restricted-mode notice lists the missing
packages and an installation command. Install them and restart the showcase.
Batch processing is disabled for a missing source; an available source is
selected at startup. If both are missing, acquisition is unavailable, but
CSV import and supplied DataFrames still work. Charting still requires its
dependencies listed above. These checks detect package presence; dependency
or provider failures during acquisition are reported in the execution console.

Choose Yahoo stocks or Binance crypto, then check or select assets in the icon
list. Search filters the list; **Select visible** checks matching assets, and
**Clear** clears all selections. Add unlisted symbols with **+ Add** (spaces
or commas separate symbols). Each source remembers its selection when you
switch. Stock symbols such as `BRK.B` and `^GSPC` retain their punctuation.
Choose a display timezone and start the batch. Both pipelines use 1h bars.
Yahoo supports 1–730 days. Binance can optionally download/update archives
before building and loading its total dataset; the gap override is opt-in.
Stop takes effect after the current asset finishes. Failed assets are logged
and the batch continues. Progress and per-asset results appear above the
chart controls, with details in the execution console. Previously loaded
datasets remain available in the chart selector, even after switching sources.

`showcase_sources.py` owns `MarketDataset`, typed source requests, adapters,
and acquisition dispatch. Neither data package depends on this application
contract. The crypto adapter loads the builder's resulting CSV through the
crypto package; the Yahoo adapter maps `StockDataResult` and its descriptor.
Both return a canonical, timezone-aware, sorted OHLCV DataFrame with actual
bounds and warnings. Missing trade counts remain nullable; they are never
converted into zero. The price/volume chart labels unavailable trade counts
and plots supplied counts without rescaling them.

Existing data can bypass acquisition entirely:

```python
from showcase_sources import MarketDataset
from showcase_pyqt_app import QApplication, MiniDumperApp

dataset = MarketDataset.from_dataframe(
    df, symbol="AAPL", interval="1h", provider="Existing"
)
app = QApplication([])
window = MiniDumperApp([dataset])
window.show()
app.exec()
```

You can also call `window.add_dataset(dataset)` on the GUI thread.
The contract takes a defensive copy; charting takes another copy because
technical analysis adds columns. `frozen=True` prevents rebinding metadata,
but does not make the owned DataFrame immutable: callers should treat it as
read-only. Cache identity includes provider, symbol, interval, and timezone;
loading that identity again replaces it and invalidates its chart cache.

**Open canonical CSV** accepts a `dt` column containing explicit timezone
offsets, plus numeric `open`, `high`, `low`, `close`, and `volume` columns.
`number_of_trades` is optional. Naive timestamps are rejected rather than
assigned an assumed timezone. The filename stem labels imported datasets.
**Save enhanced CSV** exports the chart's analysis columns and preserves
timestamp offsets without the timezone restriction of Excel export.

Settings are loaded relative to the application file. `stock_icons` and
`crypto_icons` provide PNG icons and populate the corresponding asset picker
from filename stems. Missing icons do not prevent startup: suggested assets
and custom input remain available. `spot` selects the Binance archive directory.
`preferred_time_zone` supplies the initial timezone. The previous
`open_candle` setting is not a shared adapter option.

Offline verification:

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.13 examples/check_showcase_compatibility.py
```

These checks use mocked acquisition and synthetic observations, including
stock-session gaps and missing trade counts. They do not establish live
provider availability or validate trading strategies.
