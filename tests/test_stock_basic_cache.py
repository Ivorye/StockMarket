import datetime
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, patch

import pandas as pd

import stock_basic_cache as cache
import loadStocks as ld
import stockPolicy as sp


def stocks():
    return pd.DataFrame([['000001.SZ', '000001', '测试股票', '测试股票公司', '19910403']],
                        columns=cache.REQUIRED_COLUMNS)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cached = stocks()
        self.state = None

        @contextmanager
        def guard():
            yield self.connection

        replacements = {
            '_refresh_lock': {'side_effect': guard},
            'read_cached_stocks': {'side_effect': lambda *args: self.cached.copy() if self.cached is not None else None},
            '_ensure_state_table': {},
            '_read_state': {'side_effect': lambda *args: self.state},
            '_reserve_attempt': {'side_effect': self.reserve},
            '_save_stocks': {},
            '_record_success': {'side_effect': self.success},
        }
        self.mocks = {}
        for name, options in replacements.items():
            patcher = patch.object(cache, name, **options)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(cache.db_utils, 'check_execution_status', return_value=False)
        self.old_status = patcher.start()
        self.addCleanup(patcher.stop)
        self.fetch = Mock(side_effect=lambda: stocks())

    def reserve(self, connection, next_allowed):
        self.state = (next_allowed, self.state[1] if self.state else None)

    def success(self, connection, today, source):
        self.state = (self.state[0], today)

    def test_success_today_skips_api(self):
        self.state = (datetime.datetime.now() - datetime.timedelta(hours=2),
                      datetime.date.today().strftime('%Y%m%d'))
        result = cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()
        self.assertEqual(result.attrs['stock_basic_source'], 'stocks')

    def test_legacy_success_status_skips_api(self):
        self.old_status.return_value = True
        cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()

    def test_first_refresh_succeeds_then_next_invocation_uses_cache(self):
        first = cache.get_stock_basic(self.fetch, source='manual')
        second = cache.get_stock_basic(self.fetch)
        self.fetch.assert_called_once()
        self.assertEqual(first.attrs['stock_basic_source'], 'api')
        self.assertEqual(second.attrs['stock_basic_source'], 'stocks')
        self.mocks['_record_success'].assert_called_once_with(
            self.connection, datetime.date.today().strftime('%Y%m%d'), 'manual')

    def test_previous_day_success_allows_new_listing_refresh(self):
        self.state = (datetime.datetime.now() - datetime.timedelta(hours=2),
                      (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y%m%d'))
        cache.get_stock_basic(self.fetch)
        self.fetch.assert_called_once()
        self.mocks['_save_stocks'].assert_called_once()

    def test_hourly_failure_is_not_retried_by_another_invocation(self):
        self.fetch.side_effect = RuntimeError('stock_basic 频率超限(1次/小时)')
        first = cache.get_stock_basic(self.fetch)
        second = cache.get_stock_basic(self.fetch)
        self.fetch.assert_called_once()
        self.connection.rollback.assert_called_once()
        self.mocks['_record_success'].assert_not_called()
        self.assertEqual(first.attrs['stock_basic_source'], 'stocks')
        self.assertIn('冷却至', second.attrs['stock_basic_reason'])

    def test_daily_limit_defers_until_at_least_tomorrow(self):
        self.fetch.side_effect = RuntimeError('stock_basic 频率超限(5次/天)')
        cache.get_stock_basic(self.fetch)
        tomorrow = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time())
        self.assertGreaterEqual(self.state[0], tomorrow)
        self.mocks['_record_success'].assert_not_called()

    def test_persistence_failure_does_not_mark_success(self):
        self.mocks['_save_stocks'].side_effect = RuntimeError('insert failed')
        result = cache.get_stock_basic(self.fetch)
        self.assertEqual(result.attrs['stock_basic_source'], 'stocks')
        self.mocks['_record_success'].assert_not_called()
        self.connection.rollback.assert_called_once()

    def test_cooldown_applies_across_midnight(self):
        self.state = (datetime.datetime.now() + datetime.timedelta(minutes=30),
                      (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y%m%d'))
        cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()

    def test_busy_lock_uses_cache_without_api(self):
        @contextmanager
        def busy():
            yield None

        self.mocks['_refresh_lock'].side_effect = busy
        result = cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()
        self.mocks['_ensure_state_table'].assert_not_called()
        self.assertIn('另一进程', result.attrs['stock_basic_reason'])

    def test_state_failure_does_not_bypass_rate_limit(self):
        self.mocks['_ensure_state_table'].side_effect = RuntimeError('permission denied')
        result = cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()
        self.assertIn('刷新控制不可用', result.attrs['stock_basic_reason'])

    def test_no_cache_and_cooldown_reports_error_without_request(self):
        self.cached = None
        self.state = (datetime.datetime.now() + datetime.timedelta(minutes=30), None)
        with self.assertRaisesRegex(RuntimeError, 'stocks 无缓存'):
            cache.get_stock_basic(self.fetch)
        self.fetch.assert_not_called()


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('_basic_cache', None), ('_basic_cache_date', None)):
            patcher = patch.object(sp, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_loader_delegates_without_eager_api_request(self):
        frame = stocks()
        with patch.object(cache, 'get_stock_basic', return_value=frame) as shared, \
                patch.object(ld.ts, 'pro_api') as api:
            self.assertIs(ld.getStockBasic(source='manual'), frame)
            api.assert_not_called()
            self.assertEqual(shared.call_args.kwargs['source'], 'manual')
            self.assertTrue(callable(shared.call_args.args[0]))

    def test_strategy_uses_db_then_memory_without_refresh(self):
        frame = stocks()
        with patch.object(ld, 'getStockBasicFromDB', return_value=frame) as read, \
                patch.object(ld, 'getStockBasic') as refresh:
            self.assertIs(sp._get_stock_basic(), frame)
            self.assertIs(sp._get_stock_basic(), frame)
            read.assert_called_once()
            refresh.assert_not_called()

    def test_strategy_db_failure_does_not_trigger_api(self):
        with patch.object(ld, 'getStockBasicFromDB', side_effect=RuntimeError('database unavailable')), \
                patch.object(ld, 'getStockBasic') as refresh:
            with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
                sp._get_stock_basic()
            refresh.assert_not_called()

    def test_strategy_without_cache_uses_shared_refresh(self):
        frame = stocks()
        with patch.object(ld, 'getStockBasicFromDB', return_value=None), \
                patch.object(ld, 'getStockBasic', return_value=frame) as refresh:
            self.assertIs(sp._get_stock_basic(), frame)
            refresh.assert_called_once()

    def test_previous_day_memory_cache_is_reloaded(self):
        sp._basic_cache = stocks()
        sp._basic_cache_date = datetime.date.today() - datetime.timedelta(days=1)
        fresh_cache = stocks()
        with patch.object(ld, 'getStockBasicFromDB', return_value=fresh_cache) as read:
            self.assertIs(sp._get_stock_basic(), fresh_cache)
            read.assert_called_once()


class PersistenceTests(unittest.TestCase):
    def test_new_listing_gets_unused_id_and_existing_name_is_updated(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(500, '000001.SZ')]
        frame = stocks()
        frame.loc[1] = ['000002.SZ', '000002', '新上市股票', '新上市公司', '20261020']

        cache._save_stocks(connection, frame)

        calls = cursor.execute.call_args_list
        self.assertTrue(calls[1].args[0].startswith('UPDATE stocks'))
        self.assertTrue(calls[1].args[0].endswith('WHERE id=%s'))
        self.assertEqual(calls[1].args[1][-1], 500)
        self.assertTrue(calls[2].args[0].startswith('INSERT INTO stocks'))
        self.assertEqual(calls[2].args[1][0], 501)
        self.assertEqual(calls[2].args[1][-1], '000002.SZ')
        self.assertNotIn('IGNORE', calls[2].args[0])
        connection.commit.assert_not_called()

    def test_invalid_or_empty_response_cannot_mark_refresh_success(self):
        invalid_frames = [None, pd.DataFrame(), pd.DataFrame({'ts_code': ['000001.SZ']}),
                          pd.concat([stocks(), stocks()], ignore_index=True)]
        null_frame = stocks()
        null_frame.loc[0, 'fullname'] = None
        invalid_frames.append(null_frame)
        for frame in invalid_frames:
            with self.subTest(frame=repr(frame)):
                connection = MagicMock()
                with self.assertRaises(ValueError):
                    cache._save_stocks(connection, frame)
                connection.cursor.assert_not_called()

    def test_named_lock_is_released_even_on_exception(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        with patch.object(cache.db_utils, 'connect_pymysql', return_value=connection):
            with self.assertRaisesRegex(RuntimeError, 'failure'):
                with cache._refresh_lock() as acquired:
                    self.assertIs(acquired, connection)
                    raise RuntimeError('failure')
        calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
        self.assertEqual(calls[0].args[0], 'SELECT GET_LOCK(%s, 0)')
        self.assertEqual(calls[-1].args[0], 'SELECT RELEASE_LOCK(%s)')
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
