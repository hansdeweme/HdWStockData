"""Offline HTTP, normalization, and loader contract tests."""

from copy import deepcopy
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

from hdw_stock_data import (
    YahooResponseError, EmptyDatasetError, SnapshotWriteError, YahooStockLoader,
    YahooRequestError, YahooRateLimitError, HdWStockDataError,
    DatasetNormalizationError, DatasetValidationError,
    UnsupportedIntervalError, UnsupportedLookbackError,
    MAX_LOOKBACK_DAYS, SUPPORTED_INTERVALS,
)
from hdw_stock_data.normalizer import OHLCV_COLUMNS, normalize_yahoo_chart, validate_market_dataframe
from hdw_stock_data.yahoo_client import YahooClient
from hdw_stock_data.version import VERSION


def observations():
    return {
        "meta": {"currency": "USD", "exchangeName": "NMS",
                 "exchangeTimezoneName": "America/New_York"},
        "timestamp": [int(pd.Timestamp(t).timestamp()) for t in
                      ("2026-03-06 14:30Z", "2026-03-09 13:30Z")],
        "indicators": {"quote": [{"open": [10, 11], "high": [12, 13],
                                  "low": [9, 10], "close": [11, 12],
                                  "volume": [100, 0]}]},
    }


def response(status=200, payload=None, headers=None):
    result = Mock(spec=requests.Response)
    result.status_code = status
    result.headers = headers or {}
    result.json.return_value = payload if payload is not None else {
        "chart": {"result": [observations()], "error": None}}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


def client_with(*responses, **kwargs):
    session = Mock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = responses
    return YahooClient(session=session, **kwargs), session


class YahooClientTests(unittest.TestCase):
    def test_capability_limits_before_requests(self):
        self.assertEqual(MAX_LOOKBACK_DAYS, {"1h": 730})
        self.assertEqual(SUPPORTED_INTERVALS, {"1h"})
        for kwargs, error in (({"interval": "1d"}, UnsupportedIntervalError),
                              ({"interval": ""}, UnsupportedIntervalError),
                              ({"interval": []}, UnsupportedIntervalError),
                              ({"days": 731}, UnsupportedLookbackError)):
            with self.subTest(kwargs=kwargs):
                client, session = client_with()
                with self.assertRaises(error):
                    client.fetch_chart("AAPL", **kwargs)
                session.get.assert_not_called()
                injected = Mock()
                with self.assertRaises(error):
                    YahooStockLoader(injected).load("AAPL", **kwargs)
                injected.fetch_chart.assert_not_called()

    def test_lookback_boundaries(self):
        for days in (1, 729, 730):
            client, session = client_with(response())
            client.fetch_chart("AAPL", days=days)
            params = session.get.call_args.kwargs["params"]
            margin = 300 if days == 730 else 0
            self.assertEqual(params["period2"] - params["period1"], days * 86400 - margin)
        injected = Mock()
        injected.fetch_chart.return_value = observations()
        YahooStockLoader(injected).load("AAPL")
        injected.fetch_chart.assert_called_once_with("AAPL", interval="1h", days=730,
                                                     include_prepost=False)

    def test_request_parameters(self):
        reply = response()
        client, session = client_with(reply)
        result = client.fetch_chart(" ^GSPC/TEST ", days=7,
                                    include_prepost=True, include_events=True)
        args, kwargs = session.get.call_args
        self.assertTrue(args[0].endswith("/%5EGSPC%2FTEST"))
        self.assertEqual(kwargs["timeout"], 15.0)
        params = kwargs["params"]
        self.assertEqual(params["period2"] - params["period1"], 7 * 86400)
        self.assertEqual(params["includePrePost"], "true")
        self.assertEqual(params["events"], "div,splits")
        self.assertEqual(result, observations())
        reply.close.assert_called_once()

    def test_defaults_and_user_agent(self):
        client, session = client_with(response())
        client.fetch_chart("AAPL")
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["period2"] - params["period1"], 730 * 86400 - 300)
        self.assertEqual(params["includePrePost"], "false")
        self.assertEqual(params["events"], "")
        self.assertEqual(session.headers["User-Agent"], f"hdw-stock-data/{VERSION}")
        session.headers["User-Agent"] = "custom-agent"
        YahooClient(session=session)
        self.assertEqual(session.headers["User-Agent"], "custom-agent")
        own = YahooClient()
        self.assertEqual(own.session.headers["User-Agent"], f"hdw-stock-data/{VERSION}")
        own.session.close()

    @patch("hdw_stock_data.yahoo_client.time.sleep")
    def test_network_retries_and_exhaustion(self, sleep):
        failure = requests.Timeout("offline")
        client, session = client_with(failure, failure, response())
        client.fetch_chart("AAPL")
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
        client, _ = client_with(failure, max_retries=1)
        with self.assertRaises(YahooRequestError) as caught:
            client.fetch_chart("AAPL")
        self.assertIs(caught.exception.__cause__, failure)

    @patch("hdw_stock_data.yahoo_client.time.sleep")
    def test_rate_limit_and_retry_after(self, sleep):
        client, _ = client_with(response(429, headers={"Retry-After": "3"}), response())
        client.fetch_chart("AAPL")
        sleep.assert_called_once_with(3.0)
        sleep.reset_mock()
        client, session = client_with(response(429), response(429), max_retries=2)
        with self.assertRaises(YahooRateLimitError):
            client.fetch_chart("AAPL")
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(1)
        for header in ("invalid", "-1", "nan", "inf"):
            self.assertEqual(YahooClient._retry_delay(header, 2), 4)
        with patch("hdw_stock_data.yahoo_client.datetime") as clock:
            clock.now.return_value = datetime(2026, 3, 9, tzinfo=timezone.utc)
            self.assertEqual(YahooClient._retry_delay("Mon, 09 Mar 2026 00:00:05 GMT", 0), 5)

    @patch("hdw_stock_data.yahoo_client.time.sleep")
    def test_http_failure_does_not_retry(self, sleep):
        for status in (400, 401, 402, 403, 404, 501):
            with self.subTest(status=status):
                reply = response(status)
                client, session = client_with(reply)
                with self.assertRaises(YahooRequestError) as caught:
                    client.fetch_chart("AAPL")
                self.assertIsInstance(caught.exception.__cause__, requests.HTTPError)
                self.assertEqual(session.get.call_count, 1)
                reply.close.assert_called_once()
        sleep.assert_not_called()

    @patch("hdw_stock_data.yahoo_client.time.sleep")
    def test_transient_server_retries_and_exhaustion(self, sleep):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                sleep.reset_mock()
                replies = [response(status), response(status), response()]
                client, session = client_with(*replies)
                self.assertEqual(client.fetch_chart("AAPL"), observations())
                self.assertEqual(session.get.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
                for reply in replies:
                    reply.close.assert_called_once()
                sleep.reset_mock()
                replies = [response(status), response(status)]
                client, session = client_with(*replies, max_retries=2)
                with self.assertRaisesRegex(YahooRequestError, f"HTTP {status}") as caught:
                    client.fetch_chart("AAPL")
                self.assertIs(caught.exception.__cause__, replies[-1].raise_for_status.side_effect)
                self.assertEqual(session.get.call_count, 2)
                sleep.assert_called_once_with(1)
                for reply in replies:
                    reply.close.assert_called_once()

    @patch("hdw_stock_data.yahoo_client.time.sleep")
    def test_retry_delays_are_capped(self, sleep):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                sleep.reset_mock()
                client, _ = client_with(response(status, headers={"Retry-After": "3600"}), response())
                client.fetch_chart("AAPL")
                sleep.assert_called_once_with(30.0)
        with patch("hdw_stock_data.yahoo_client.datetime") as clock:
            clock.now.return_value = datetime(2026, 3, 9, tzinfo=timezone.utc)
            self.assertEqual(YahooClient._retry_delay("Mon, 09 Mar 2026 01:00:00 GMT", 0), 30.0)
        for header in (None, "invalid", "-1", "nan", "inf"):
            self.assertEqual(YahooClient._retry_delay(header, 10000), 30.0)
        self.assertEqual(YahooClient._retry_delay("0", 10), 0)
        sleep.reset_mock()
        client, _ = client_with(*([requests.Timeout("offline")] * 6), response(), max_retries=7)
        client.fetch_chart("AAPL")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4, 8, 16, 30.0])

    def test_invalid_json_and_structure(self):
        for payload in ([], {"chart": []}, {"chart": {"error": "bad symbol"}},
                        {"chart": {"result": []}}, {"chart": {"result": [42]}},
                        {"chart": {"result": {"unexpected": 1}}}):
            client, _ = client_with(response(payload=payload))
            with self.assertRaises(YahooResponseError):
                client.fetch_chart("AAPL")
        reply = response()
        reply.json.side_effect = ValueError("bad JSON")
        client, _ = client_with(reply)
        with self.assertRaises(YahooResponseError) as caught:
            client.fetch_chart("AAPL")
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        reply.close.assert_called_once()

    def test_invalid_arguments(self):
        for kwargs in ({"max_retries": 0}, {"max_retries": True},
                       {"timeout": 0}, {"timeout": float("nan")}):
            with self.assertRaises(ValueError):
                YahooClient(**kwargs)
        client, session = client_with()
        for kwargs in ({"days": 0}, {"days": True}, {"days": 1.5}):
            with self.assertRaises(ValueError):
                client.fetch_chart("AAPL", **kwargs)
        session.get.assert_not_called()


class StockDataTests(unittest.TestCase):
    def test_normalization_preserves_observations(self):
        raw = observations()
        original = deepcopy(raw)
        result = normalize_yahoo_chart(raw)
        self.assertEqual(tuple(result.columns), OHLCV_COLUMNS)
        self.assertEqual(result.index.name, "dt")
        self.assertEqual(str(result.index.tz), "UTC")
        self.assertEqual([int(t.timestamp()) for t in result.index], raw["timestamp"])
        self.assertEqual(result.volume.tolist(), [100., 0.])
        self.assertTrue(result.number_of_trades.isna().all())
        self.assertEqual(result.number_of_trades.dtype, pd.Float64Dtype())
        self.assertEqual(raw, original)

    def test_sort_duplicate_and_bad_rows(self):
        raw = observations()
        raw["timestamp"] = [raw["timestamp"][1], raw["timestamp"][0], raw["timestamp"][0]]
        for values in raw["indicators"]["quote"][0].values():
            values.append(values[1])
        raw["indicators"]["quote"][0]["close"][-1] = 11.5
        result = normalize_yahoo_chart(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]["close"], 11.5)
        raw = observations()
        raw["indicators"]["quote"][0]["open"][0] = None
        self.assertEqual(len(normalize_yahoo_chart(raw)), 1)
        raw["indicators"]["quote"][0]["close"][1] = None
        with self.assertRaises(EmptyDatasetError):
            normalize_yahoo_chart(raw)

    def test_invalid_and_empty_chart_data(self):
        raw = observations()
        raw["indicators"]["quote"][0]["volume"] = [1]
        with self.assertRaises(DatasetNormalizationError):
            normalize_yahoo_chart(raw)
        raw = observations()
        raw["timestamp"] = []
        with self.assertRaises(EmptyDatasetError):
            normalize_yahoo_chart(raw)

    def test_empty_timestamps_without_quote_data(self):
        for raw in ({}, {"meta": {}}, {"timestamp": None}, {"timestamp": []}):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(EmptyDatasetError, "Yahoo returned no timestamps"):
                    normalize_yahoo_chart(raw)
                client, _ = client_with(response(payload={
                    "chart": {"result": [raw], "error": None}}))
                with self.assertRaises(EmptyDatasetError):
                    YahooStockLoader(client).load("AAPL")

    def test_nonempty_timestamps_require_quote_data(self):
        for indicators in (None, {}, {"quote": []}):
            with self.subTest(indicators=indicators):
                with self.assertRaisesRegex(DatasetNormalizationError, "missing quote data"):
                    normalize_yahoo_chart({"timestamp": [1], "indicators": indicators})

    def test_invalid_timestamp_types_are_not_empty_datasets(self):
        for timestamps in (False, 0, "", {}):
            with self.subTest(timestamps=timestamps):
                raw = observations()
                raw["timestamp"] = timestamps
                with self.assertRaises(DatasetNormalizationError):
                    normalize_yahoo_chart(raw)

    def test_normalization_and_validation_errors(self):
        original = ValueError("conversion failed")
        with patch("hdw_stock_data.normalizer.pd.to_numeric", side_effect=original):
            with self.assertRaises(DatasetNormalizationError) as caught:
                normalize_yahoo_chart(observations())
            self.assertIs(caught.exception.__cause__, original)
        canonical = normalize_yahoo_chart(observations())
        for invalid in (canonical.drop(columns="close"),
                        canonical.set_axis(canonical.index.tz_localize(None)),
                        canonical.assign(volume=-1)):
            with self.assertRaises(DatasetValidationError):
                validate_market_dataframe(invalid)

    def test_missing_volume_and_optional_extra_columns(self):
        raw = observations()
        raw["indicators"]["quote"][0]["volume"][0] = None
        df = normalize_yahoo_chart(raw)
        self.assertEqual(len(df), 2)
        self.assertTrue(pd.isna(df.iloc[0]["volume"]))
        validate_market_dataframe(df.drop(columns="number_of_trades"))
        validate_market_dataframe(df.assign(extra="allowed"))

    def test_invalid_ohlc_relationships_and_nonfinite_values(self):
        for column, value in (("high", 5), ("low", 20), ("volume", -1),
                              ("open", float("inf")), ("volume", float("inf"))):
            with self.subTest(column=column, value=value):
                raw = observations()
                raw["indicators"]["quote"][0][column][0] = value
                with self.assertRaises(DatasetValidationError):
                    normalize_yahoo_chart(raw)

    def test_invalid_timestamps(self):
        raw = observations()
        raw["timestamp"][0] = "invalid"
        with self.assertRaises(DatasetNormalizationError):
            normalize_yahoo_chart(raw)
        raw["timestamp"][0] = None
        with self.assertRaises(DatasetValidationError):
            normalize_yahoo_chart(raw)

    def test_exception_hierarchy(self):
        self.assertTrue(issubclass(YahooRateLimitError, YahooRequestError))
        for error in (YahooRequestError, YahooResponseError, EmptyDatasetError,
                      DatasetNormalizationError, DatasetValidationError, SnapshotWriteError):
            self.assertEqual(error.__bases__, (HdWStockDataError,))

    def test_loader_descriptor_timezone_and_snapshot(self):
        client = Mock()
        client.fetch_chart.return_value = observations()
        loader = YahooStockLoader(client)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            target = Path(directory) / "nested"
            path = target / "AAPL-yahoo-1h-20260306T143000Z--20260309T133000Z.csv"
            result = loader.load("AAPL", days=7, preferred_tz="Europe/Amsterdam", save_to=target)
            self.assertEqual(result.dataframe.index.hour.tolist(), [15, 14])
            client.fetch_chart.assert_called_once_with("AAPL", days=7, interval="1h",
                                                       include_prepost=False)
            self.assertIs(result.data, result.dataframe)
            saved = pd.read_csv(path)
            self.assertTrue(saved.number_of_trades.isna().all())
            self.assertEqual(pd.to_datetime(saved.dt, utc=True).tolist(), result.dataframe.index.tolist())
            descriptor = result.descriptor
            self.assertEqual((descriptor.symbol, descriptor.provider, descriptor.rows), ("AAPL", "yahoo", 2))
            self.assertEqual(descriptor.currency, "USD")
            self.assertEqual(descriptor.exchange, "NMS")
            self.assertEqual(descriptor.actual_start, result.dataframe.index[0])
            self.assertEqual(descriptor.actual_end, result.dataframe.index[-1])
            self.assertFalse(descriptor.adjusted)
            self.assertEqual(result.filepath, path)
            self.assertEqual(result.warnings, ())
            with self.assertRaises(SnapshotWriteError):
                loader.load("AAPL", save_to=path)
        self.assertEqual(str(loader.load("AAPL").dataframe.index.tz), "UTC")
        self.assertEqual(str(loader.load("AAPL", preferred_tz="America/New_York").dataframe.index.tz), "America/New_York")

    def test_cleaned_bounds_and_missing_metadata(self):
        raw = observations()
        raw["meta"] = {}
        raw["indicators"]["quote"][0]["open"][0] = None
        client = Mock()
        client.fetch_chart.return_value = raw
        result = YahooStockLoader(client).load("AAPL")
        self.assertEqual(result.descriptor.rows, 1)
        self.assertEqual(result.descriptor.actual_start, result.descriptor.actual_end)
        self.assertEqual(str(result.descriptor.actual_start.tz), "UTC")
        self.assertIsNone(result.descriptor.currency)
        self.assertIsNone(result.descriptor.exchange)
        self.assertIsNone(result.filepath)
        self.assertEqual(len(result.warnings), 1)

    def test_exchange_name_preference(self):
        raw = observations()
        raw["meta"]["fullExchangeName"] = "NasdaqGS"
        client = Mock()
        client.fetch_chart.return_value = raw
        self.assertEqual(YahooStockLoader(client).load("AAPL").descriptor.exchange, "NasdaqGS")

    def test_loader_validates_before_retrieval(self):
        client = Mock()
        loader = YahooStockLoader(client)
        for kwargs in ({"symbol": " "}, {"days": 0}, {"days": True},
                       {"preferred_tz": "Invalid/Zone"},
                       {"preferred_tz": None}, {"include_prepost": 1},
                       {"save_to": 42}, {"save_to": ""}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    loader.load(**({"symbol": "AAPL"} | kwargs))
        client.fetch_chart.assert_not_called()

    def test_snapshot_symbol_components(self):
        client = Mock()
        client.fetch_chart.return_value = observations()
        loader = YahooStockLoader(client)
        for symbol in ("^", "...", "---", "^.-/\\*"):
            with self.subTest(symbol=symbol):
                with self.assertRaisesRegex(ValueError, "usable snapshot filename component"):
                    loader.load(symbol, save_to="snapshots")
                client.fetch_chart.assert_not_called()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            for symbol, component in (("^gspc", "GSPC"), (".-aapl-.", "AAPL"),
                                      ("brk.b", "BRK.B"), ("btc-usd", "BTC-USD"),
                                      ("a_b", "A_B"), ("a/b\\c*", "ABC")):
                with self.subTest(symbol=symbol):
                    result = loader.load(symbol, save_to=directory)
                    self.assertEqual(result.filepath.name,
                                     f"{component}-yahoo-1h-20260306T143000Z--20260309T133000Z.csv")
                    self.assertTrue(result.filepath.is_file())
                    self.assertEqual(result.descriptor.symbol, symbol)
                    self.assertEqual(client.fetch_chart.call_args.args, (symbol,))

    def test_atomic_snapshot_preserves_previous_file_on_failure(self):
        client = Mock()
        client.fetch_chart.return_value = observations()
        loader = YahooStockLoader(client)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            first = loader.load("^GSPC", interval="1h", save_to=directory)
            self.assertEqual(first.filepath.name, "GSPC-yahoo-1h-20260306T143000Z--20260309T133000Z.csv")
            original = first.filepath.read_bytes()
            for target in ("hdw_stock_data.loader.os.replace", "pandas.DataFrame.to_csv"):
                with self.subTest(target=target):
                    with patch(target, side_effect=OSError("write failed")):
                        with self.assertRaises(SnapshotWriteError) as caught:
                            loader.load("^GSPC", interval="1h", save_to=directory)
                    self.assertIsInstance(caught.exception.__cause__, OSError)
                    self.assertEqual(first.filepath.read_bytes(), original)
                    self.assertEqual(list(Path(directory).iterdir()), [first.filepath])
            client.fetch_chart.return_value["indicators"]["quote"][0]["close"][0] = 10.5
            loader.load("^GSPC", interval="1h", save_to=directory)
            self.assertNotEqual(first.filepath.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
