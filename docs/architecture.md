# Architecture

`YahooStockLoader.load()` validates arguments, calls `YahooClient.fetch_chart()`,
normalizes chart JSON, converts UTC to the requested timezone, reads metadata,
optionally writes a snapshot, and returns `StockDataResult`.

| Module | Responsibility |
| --- | --- |
| `yahoo_client.py` | HTTP sessions, retries, capability limits, raw JSON validation |
| `normalizer.py` | Canonical observations and market-data validation |
| `loader.py` | Public facade, metadata, timezone conversion, atomic snapshots |
| `result.py` | Frozen descriptor and result dataclasses |
| `exceptions.py` | Package exception hierarchy |
| `version.py` | Version 0.1.0 |
| `__init__.py` | Documented public exports |

The package does not import the crypto project, chart code, settings files, or
GUI libraries. Its DataFrame is compatible with the crypto analysis contract.

Snapshots use sanitized symbols and UTC bounds, for example
`GSPC-yahoo-1h-20260306T143000Z--20260309T133000Z.csv`. A unique temporary file
in the destination directory is flushed and replaced atomically. On failure,
an existing snapshot remains intact and temporary-file cleanup is attempted.
Different symbols can sanitize to the same name; callers should use separate
directories if such collisions are possible in their symbol selection.
