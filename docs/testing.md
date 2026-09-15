# Testing and release checklist

## Offline regression suite

Run `python -m unittest discover -s tests -v` from the project root. Tests cover
HTTP parameters and retries, capability boundaries, invalid payloads, OHLCV
normalization and validation, DST conversion, descriptors, and atomic snapshot
success and failure. No HTTP requests are made by these tests.

Discovery also runs the showcase contract and adapter tests. GUI tests are
skipped when PyQt6 is unavailable; crypto adapter checks are skipped when the
optional crypto package is unavailable. For full GUI and chart verification,
use Python 3.12 or newer and install `python -m pip install -e ".[dev,showcase]"`,
then run discovery and `python -m tests.check_showcase_compatibility`.

## Planned live checks

Run `python -m examples.test_assets` for the initial live check of `AAPL`,
`ASML.AS`, `^GSPC`, and `^VIX`. It requests five days of hourly bars, reports
each result independently, and returns a nonzero exit status if any symbol
fails. Add `--save-to snapshots` to save CSV files. This script is outside the
offline test suite and only contacts Yahoo when explicitly executed.

- Retrieve a short range for a stock and an index, including a symbol with `^`.
- Compare returned hourly timestamps and prices with the provider.
- Request 730 days; record actual bounds, omissions, and provider failures.
- Check different exchanges, currencies, market closures, DST, and extended hours.
- Observe naturally occurring rate limits; do not generate load to provoke them.
- Save and reload CSV across DST boundaries; compare UTC instants and OHLCV.

Use `python -m examples.fetch_stock AAPL --days 5` for a small manual smoke
test. Add `--save-to snapshots` to exercise snapshot creation. Requests are
explicitly opt-in; no tests depend on current prices or network availability.

## Before release

- Build wheel and source distribution, and inspect their contents.
- Install the wheel into a clean Python environment and rerun tests.
- Verify supported Python versions and operating systems.
- Record live-check dates, symbols, intervals, actual bounds, and errors.
- Publish only after review; creating this project does not publish a release.
