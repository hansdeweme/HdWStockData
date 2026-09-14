"""Offline showcase chart smoke test; no GUI windows or network requests.

Run from the project root:
    py -3.13 examples/check_showcase_compatibility.py
Use --chart-source PATH to select the directory containing ta_charts.py
(defaults to this checkout).
"""

import argparse
import contextlib
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chart-source', type=Path, default=root)
    args = parser.parse_args()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(args.chart_source.resolve()))
    os.environ.setdefault('NUMBA_DISABLE_JIT', '1')
    import showcase_pyqt_app as showcase
    import plotly.io as pio
    from hdw_stock_data.normalizer import normalize_yahoo_chart
    from showcase_sources import MarketDataset

    # Hourly stock-session observations, including overnight/weekend gaps.
    index = pd.DatetimeIndex([
        day + pd.Timedelta(hours=hour, minutes=30)
        for day in pd.bdate_range('2026-01-05', periods=100, tz='UTC')
        for hour in range(14, 21)
    ])
    x = np.arange(len(index))
    close = 100 + x * 0.02 + np.sin(x / 5)
    raw = {
        'timestamp': [int(t.timestamp()) for t in index],
        'indicators': {'quote': [{
            'open': (close - 0.1).tolist(), 'high': (close + 1).tolist(),
            'low': (close - 1).tolist(), 'close': close.tolist(),
            'volume': (1000 + x).tolist(),
        }]},
    }
    yahoo = normalize_yahoo_chart(raw)
    failures = []
    for provider in ('yahoo', 'binance_counts'):
        df = yahoo.copy(deep=True)
        if provider == 'binance_counts':
            df['number_of_trades'] = np.arange(len(df)) + 1
        original = df.copy(deep=True)
        dataset = MarketDataset.from_dataframe(df, symbol='AAPL', provider=provider)
        key = (provider, 'AAPL', '1h', 'UTC')
        host = SimpleNamespace(
            chart_info_cache={}, datasets={key: dataset},
        )
        with contextlib.redirect_stdout(io.StringIO()):
            info = showcase.MiniDumperApp.build_ta_charts(host, key)
        assert len(info.df) == len(df)
        assert showcase.MiniDumperApp.build_ta_charts(host, key) is info
        figures = []

        def capture(fig, *args, **kwargs):
            pio.to_json(fig, validate=True)
            figures.append(fig)

        actions = {
            'price_volume': lambda: info.plot_pricevol(48),
            'raw': lambda: info.plot_raw(30),
            'keltner': lambda: (info.do_keltner(), info.plot_keltner(30)),
            'sma': lambda: (info.calc_sma_ema(), info.plot_sma(30)),
            'simulation': lambda: info.do_sim(30),
            'gaussian': lambda: info.do_gauss(30),
        }
        for name, action in actions.items():
            before = len(figures)
            try:
                with patch.object(pio, 'show', side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
                    action()
                assert len(figures) > before, 'No figure produced'
                if name == 'price_volume':
                    if provider == 'yahoo':
                        assert not any(trace.type == 'bar' for trace in figures[-1].data)
                        assert any(a.text == 'Trade counts unavailable' for a in figures[-1].layout.annotations)
                    else:
                        trades = next(trace for trace in figures[-1].data if trace.name == 'Trades')
                        np.testing.assert_array_equal(trades.y, info._last_period('48h')['number_of_trades'])
                print(f'PASS {provider}: {name} (figure serialized)')
            except Exception as exc:
                failures.append((provider, name, str(exc)))
                print(f'FAIL {provider}: {name}: {type(exc).__name__}: {exc}')
        pd.testing.assert_frame_equal(df, original)
        if provider == 'yahoo':
            assert info.df.number_of_trades.isna().all()
            assert str(info.df.number_of_trades.dtype) == 'Float64'
    print(f'Chart source: {args.chart_source.resolve()}')
    print(f'{len(failures)} failure(s); synthetic data, no GUI rendering or live retrieval tested.')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
