"""Opt-in live Yahoo smoke test: python -m examples.fetch_stock AAPL --days 5."""

import argparse

from hdw_stock_data import HdWStockDataError, YahooStockLoader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--save-to")
    args = parser.parse_args()
    try:
        result = YahooStockLoader().load(
            args.symbol, days=args.days, preferred_tz=args.timezone,
            save_to=args.save_to,
        )
    except (HdWStockDataError, ValueError) as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")
    print(result.descriptor)
    print(result.dataframe.tail())
    if result.filepath:
        print(result.filepath)
    for warning in result.warnings:
        print(warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
