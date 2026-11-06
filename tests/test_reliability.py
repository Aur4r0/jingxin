import unittest
from unittest.mock import MagicMock, patch
import ccxt
from app.security import hash_password, verify_password
from app.engine import sync_positions
from app.runtime_status import snapshot
from app.exchange_errors import explain

class ReliabilityTests(unittest.TestCase):
    def test_failed_fetch_does_not_clear_positions(self):
        db=MagicMock()
        with patch('app.engine.SessionLocal',return_value=db), patch('app.engine.fetch_positions',side_effect=RuntimeError('网络连接失败')):
            self.assertFalse(sync_positions())
        db.query.assert_not_called()
        db.rollback.assert_called_once()
        self.assertFalse(snapshot()['positions']['ok'])
    def test_empty_success_clears_positions(self):
        db=MagicMock()
        with patch('app.engine.SessionLocal',return_value=db),patch('app.engine.fetch_positions',return_value=[]):
            self.assertTrue(sync_positions())
        db.query.return_value.delete.assert_called_once()
        db.commit.assert_called_once()
        self.assertTrue(snapshot()['positions']['ok'])
    def test_password_hash(self):
        encoded=hash_password('test-password-123')
        self.assertTrue(verify_password('test-password-123',encoded))
        self.assertFalse(verify_password('wrong',encoded))
        self.assertFalse(verify_password('wrong','invalid'))
    def test_errors_redacted(self):
        self.assertIn('网络',explain(ccxt.NetworkError('secret-token')))
        self.assertNotIn('secret-token',explain(ccxt.AuthenticationError('secret-token')))
    def test_missing_market_data_never_calls_ai_or_places_order(self):
        from app.engine import _run_strategy_for_symbol
        from types import SimpleNamespace
        db=MagicMock()
        with patch('app.engine.fetch_ohlcv',return_value=[]),patch('app.engine.fetch_ticker',return_value={}),patch('app.engine.call_ai') as ai,patch('app.engine.place_order') as order:
            _run_strategy_for_symbol(db,SimpleNamespace(id=1),'BTC-USDT-SWAP',100,100,[])
        ai.assert_not_called();order.assert_not_called();db.commit.assert_called_once()
    def test_strategy_execution_is_mutually_exclusive(self):
        from app.engine import run_strategy, _strategy_execution_locks
        from threading import Lock
        lock=Lock();lock.acquire();_strategy_execution_locks[123456]=lock
        with patch('app.engine._run_strategy_impl') as execute:
            run_strategy(123456)
            execute.assert_not_called()
        lock.release()
    def test_session_source_check(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client=TestClient(app)
        response=client.post('/login',data={'username':'x','password':'x'},headers={'origin':'https://unrelated.invalid'})
        self.assertEqual(response.status_code,403)
    def test_instance_lock_excludes_second_holder(self):
        import tempfile,os
        from app.instance_lock import acquire
        with tempfile.TemporaryDirectory() as folder:
            old=os.getcwd()
            try:
                os.chdir(folder)
                first=acquire()
                try:
                    with self.assertRaises(RuntimeError):acquire()
                finally:first.close()
                acquire().close()
            finally:os.chdir(old)
