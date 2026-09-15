"""Offline application contract, adapter, and offscreen Qt checks."""
import io
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from examples.showcase_sources import (MarketDataset, StockSourceAdapter, StockRequest,
    CryptoSourceAdapter, CryptoRequest, load_csv, source_availability)


def frame():
    return pd.DataFrame({'open': [10., 11.], 'high': [12., 13.],
                         'low': [9., 10.], 'close': [11., 12.], 'volume': [100., 200.]},
                        index=pd.date_range('2026-03-09', periods=2, freq='h', tz='UTC', name='dt'))


class ContractTests(unittest.TestCase):
    def test_source_presence_without_importing_pipelines(self):
        for stock, crypto in ((True, True), (True, False), (False, True), (False, False)):
            with self.subTest(stock=stock, crypto=crypto), patch(
                    'examples.showcase_sources.find_spec', side_effect=[object() if stock else None,
                                                              object() if crypto else None]) as probe:
                self.assertEqual(source_availability(), (stock, crypto))
                self.assertEqual([call.args[0] for call in probe.call_args_list],
                                 ['hdw_stock_data', 'hdw_crypto_data'])

    def test_ownership_and_missing_trades(self):
        df = frame()
        dataset = MarketDataset.from_dataframe(df, symbol='^GSPC')
        df.iloc[0, 0] = 999
        self.assertEqual(dataset.dataframe.iloc[0].open, 10)
        self.assertTrue(dataset.dataframe.number_of_trades.isna().all())
        self.assertEqual(str(dataset.dataframe.number_of_trades.dtype), 'Float64')

    def test_invalid_index_and_metadata(self):
        for df in (frame().iloc[::-1], frame().set_axis(pd.RangeIndex(2)),
                   frame().set_axis(frame().index.tz_localize(None))):
            with self.subTest(index=df.index), self.assertRaises(ValueError):
                MarketDataset.from_dataframe(df, symbol='AAPL')
        df = frame()
        with self.assertRaises(ValueError):
            MarketDataset(df, 'AAPL', '1h', 'Yahoo', 'UTC', df.index[-1], df.index[-1])

    def test_stock_adapter_maps_result(self):
        df = frame()
        descriptor = SimpleNamespace(symbol='^GSPC', interval='1h', timezone='UTC',
                                     actual_start=df.index.min(), actual_end=df.index.max())
        loader = Mock()
        loader.load.return_value = SimpleNamespace(dataframe=df, descriptor=descriptor, warnings=('cleaned',))
        dataset = StockSourceAdapter(loader).load(StockRequest('^GSPC', days=7))
        loader.load.assert_called_once_with('^GSPC', interval='1h', days=7, preferred_tz='UTC')
        self.assertEqual((dataset.provider, dataset.symbol, dataset.warnings), ('Yahoo', '^GSPC', ('cleaned',)))

    def test_csv_roundtrip_and_naive_rejection(self):
        df = frame()
        df['number_of_trades'] = pd.Series(pd.NA, index=df.index, dtype='Float64')
        dataset = load_csv(io.StringIO(df.to_csv()), symbol='AAPL', timezone='Europe/Amsterdam')
        self.assertTrue(dataset.dataframe.number_of_trades.isna().all())
        self.assertEqual(dataset.actual_start, df.index[0])
        self.assertEqual(dataset.timezone, 'Europe/Amsterdam')
        df.index = df.index.tz_localize(None)
        with self.assertRaisesRegex(ValueError, 'timezone offset'):
            load_csv(io.StringIO(df.to_csv()), symbol='AAPL')

    def test_crypto_adapter_pipeline(self):
        try:
            import hdw_crypto_data
        except ImportError:
            self.skipTest('Optional crypto package not installed')
        df = frame()
        df['number_of_trades'] = [25, 30]
        for archives in (False, True):
            with self.subTest(archives=archives), \
                 patch('hdw_crypto_data.binance_vision_dumper.BinanceVisionDumper') as dumper, \
                 patch('hdw_crypto_data.total_dataset_builder.TotalDatasetBuilder') as builder, \
                 patch('hdw_crypto_data.total_dataset_loader.TotalDatasetLoader') as loader:
                builder.return_value.build.return_value = SimpleNamespace(filepath='total.csv')
                loader.return_value.load_total_dataframe.return_value = df
                dataset = CryptoSourceAdapter().load(CryptoRequest('BTC', {'spot': 'spot'}, download_archives=archives))
                self.assertEqual(dataset.symbol, 'BTCUSDT')
                self.assertEqual(dataset.dataframe.number_of_trades.tolist(), [25, 30])
                self.assertEqual(dumper.called, archives)
                builder.return_value.build.assert_called_once()
                loader.return_value.load_total_dataframe.assert_called_once_with(
                    file_path='total.csv', mode='ta', preferred_tz='UTC')
                self.assertEqual(builder.call_args.args[1]['full_spot'], str(Path('spot').resolve()))


class ShowcaseGuiTests(unittest.TestCase):
    def setUp(self):
        availability = patch('examples.showcase_pyqt_app.source_availability', return_value=(True, True))
        availability.start()
        self.addCleanup(availability.stop)

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from examples.showcase_pyqt_app import QApplication
        except ImportError as exc:
            raise unittest.SkipTest(str(exc))
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_packages_restrict_acquisition_but_allow_existing_data(self):
        from examples.showcase_pyqt_app import MiniDumperApp
        for available in ((True, True), (True, False), (False, True), (False, False)):
            with self.subTest(available=available), patch(
                    'examples.showcase_pyqt_app.source_availability', return_value=available):
                window = MiniDumperApp()
                try:
                    self.assertEqual(window.dependency_notice.isHidden(), all(available))
                    self.assertEqual(window.source_combo.currentIndex(),
                                     1 if available == (False, True) else 0)
                    for index, package in enumerate(('hdw_stock_data', 'hdw_crypto_data')):
                        window.source_combo.setCurrentIndex(index)
                        window.set_all_checked(True)
                        self.assertEqual(window.load_button.isEnabled(), available[index])
                        if not available[index]:
                            self.assertIn(package, window.dependency_notice.text())
                            self.assertIn('-m pip install', window.dependency_notice.text())
                            with patch('examples.showcase_pyqt_app.QMessageBox.warning') as warning:
                                window.start_processing()
                                warning.assert_called_once()
                            self.assertIsNone(window.worker)
                    self.assertTrue(window.csv_button.isEnabled())
                    window.add_dataset(MarketDataset.from_dataframe(frame(), symbol='Existing'))
                    self.assertTrue(window.show_chart_btn.isEnabled())
                    self.assertEqual(window.chart_asset_combo.count(), 1)
                finally:
                    window.close()

    def test_direct_dataset_cache_and_source_selection(self):
        from examples.showcase_pyqt_app import MiniDumperApp
        first = MarketDataset.from_dataframe(frame(), symbol='AAPL', provider='Yahoo')
        window = MiniDumperApp([first])
        try:
            self.assertEqual(window.chart_asset_combo.count(), 1)
            self.assertIn('unavailable', window.metadata_label.text())
            window.show()
            self.app.processEvents()
            with patch('examples.ta_charts.TACharts') as charts:
                key = window.chart_asset_combo.currentData()
                window.build_ta_charts(key)
                window.build_ta_charts(key)
                charts.assert_called_once()
                charts.call_args.args[1].iloc[0, 0] = 999
                self.assertEqual(first.dataframe.iloc[0].open, 10)
                window.add_dataset(first)
                self.assertEqual(window.chart_asset_combo.count(), 1)
                self.assertNotIn(key, window.chart_info_cache)
            window.add_dataset(MarketDataset.from_dataframe(frame(), symbol='AAPL', provider='CSV'))
            self.assertEqual(window.chart_asset_combo.count(), 2)
            window.source_combo.setCurrentIndex(1)
            self.assertTrue(window.archive_check.isEnabled())
            self.assertFalse(window.days_spin.isEnabled())
        finally:
            window.close()

    def test_worker_delivers_dataset_and_continues_after_failure(self):
        from examples.showcase_pyqt_app import PipelineWorker
        dataset = MarketDataset.from_dataframe(frame(), symbol='AAPL')
        controller = Mock()
        controller.load.side_effect = [ValueError('failed'), dataset]
        worker = PipelineWorker([StockRequest('BAD'), StockRequest('AAPL')], controller)
        ready, failed = [], []
        worker.dataset_ready.connect(ready.append)
        worker.failed.connect(failed.append)
        worker.run()
        self.assertEqual(ready, [dataset])
        self.assertEqual(failed, ['BAD: failed'])

    def test_icon_picker_filtering_and_source_selections(self):
        from PyQt6.QtGui import QImage, QColor
        from examples.showcase_pyqt_app import MiniDumperApp
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            for kind, symbols in (('stocks', ('AAPL', 'BRK.B')), ('crypto', ('btc', 'eth'))):
                (root / kind).mkdir()
                for symbol in symbols:
                    image = QImage(24, 24, QImage.Format.Format_RGB32)
                    image.fill(QColor('blue'))
                    self.assertTrue(image.save(str(root / kind / f'{symbol}.png')))
            settings = {'stock_icons': str(root / 'stocks'), 'crypto_icons': str(root / 'crypto'),
                        'spot': str(root / 'spot'), 'preferred_time_zone': 'UTC'}
            with patch.object(MiniDumperApp, 'load_settings', return_value=settings):
                window = MiniDumperApp()
            try:
                self.assertEqual(window.asset_list.count(), 2)
                self.assertFalse(window.asset_list.item(0).icon().isNull())
                window.set_all_checked(False)
                window.search_bar.setText('BRK')
                window.set_all_checked(True)
                self.assertEqual(window.selected_symbols(), ['BRK.B'])
                window.symbol_input.setText('^GSPC')
                window.add_custom_assets()
                self.assertIn('^GSPC', window.selected_symbols())
                window.source_combo.setCurrentIndex(1)
                self.assertEqual(window.asset_list.count(), 2)
                self.assertEqual(window.selected_symbols(), ['BTC'])
                self.assertFalse(window.asset_list.item(0).icon().isNull())
                window.source_combo.setCurrentIndex(0)
                self.assertEqual(set(window.selected_symbols()), {'BRK.B', '^GSPC'})
                self.assertIn('stock', window.asset_group.title())
            finally:
                window.close()

    def test_selected_assets_run_worker_and_enable_charts(self):
        from PyQt6.QtTest import QTest
        from examples.showcase_pyqt_app import MiniDumperApp
        settings = {'spot': 'spot', 'preferred_time_zone': 'UTC'}
        with patch.object(MiniDumperApp, 'load_settings', return_value=settings):
            window = MiniDumperApp()
        try:
            window.set_all_checked(False)
            window.symbol_input.setText('BRK.B ^GSPC')
            window.add_custom_assets()
            dataset = MarketDataset.from_dataframe(frame(), symbol='BRK.B', provider='Yahoo')
            def acquire(request):
                if request.symbol == 'BRK.B':
                    return dataset
                raise ValueError('provider unavailable')
            with patch('examples.showcase_pyqt_app.AcquisitionController') as factory:
                factory.return_value.load.side_effect = acquire
                window.start_processing()
                self.assertFalse(window.asset_group.isEnabled())
                deadline = time.monotonic() + 5
                while window._batch_active and time.monotonic() < deadline:
                    QTest.qWait(10)
                self.assertFalse(window._batch_active)
                calls = factory.return_value.load.call_args_list
                self.assertEqual({c.args[0].symbol for c in calls}, {'BRK.B', '^GSPC'})
                self.assertTrue(all(isinstance(c.args[0], StockRequest) for c in calls))
            statuses = {window.table.item(row, 0).text(): window.table.item(row, 2).text()
                        for row in range(window.table.rowCount())}
            self.assertEqual(statuses, {'BRK.B': 'Ready', '^GSPC': 'Failed'})
            self.assertEqual(window.progress_bar.value(), 2)
            self.assertTrue(window.show_chart_btn.isEnabled())
            self.assertTrue(window.chart_type_combo.isEnabled())
            self.assertTrue(window.asset_group.isEnabled())
            with patch('examples.ta_charts.TACharts') as charts:
                window.chart_type_combo.setCurrentIndex(1)
                window.show_selected_chart()
                charts.return_value.plot_pricevol.assert_called_once_with(96)
            window.source_combo.setCurrentIndex(1)
            self.assertEqual(window.chart_asset_combo.count(), 1)
            window.set_all_checked(False)
            window.symbol_input.setText('ETH')
            window.add_custom_assets()
            with patch('examples.showcase_pyqt_app.AcquisitionController') as factory:
                factory.return_value.load.return_value = MarketDataset.from_dataframe(frame(), symbol='ETHUSDT', provider='Binance')
                window.start_processing()
                deadline = time.monotonic() + 5
                while window._batch_active and time.monotonic() < deadline:
                    QTest.qWait(10)
                self.assertFalse(window._batch_active)
                self.assertIsInstance(factory.return_value.load.call_args.args[0], CryptoRequest)
            self.assertEqual(window.chart_asset_combo.count(), 2)
        finally:
            if window.worker and window.worker.isRunning():
                window.worker.requestInterruption()
                window.worker.wait(5000)
            window.close()


if __name__ == '__main__':
    unittest.main()
