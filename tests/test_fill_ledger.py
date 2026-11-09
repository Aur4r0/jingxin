import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from app.models import Base, ExecutionFill, SystemConfig, Trade, Strategy
from app.fill_ledger import store_fills, fill_summary, fill_view, sync_demo_fills, account_key
from app.config import encrypt_value


def fill(**overrides):
    row = dict(instId='BTC-USDT-SWAP', ordId='order-1', tradeId='fill-1', billId='bill-1',
               side='sell', posSide='long', subType='5', fillPx='75358.2', fillSz='0.13',
               fillPnl='-2.8532', fee='-0.05', feeCcy='USDT', ts='1793948400000')
    row.update(overrides)
    return row


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.cfg = SystemConfig(id=1, okx_simulated=True,
            okx_sim_api_key_enc=encrypt_value('test-key'), okx_sim_secret_key_enc=encrypt_value('test-secret'),
            okx_sim_passphrase_enc=encrypt_value('test-pass'))
        self.db.add(self.cfg)
        self.db.commit()
        self.scope = account_key(self.cfg)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_actual_fills_deduplicated_no_contract_multiplier_twice(self):
        self.assertEqual(store_fills(self.db, [fill(), fill()], self.scope), 1)
        self.db.commit()
        rows = self.db.query(ExecutionFill).all()
        result = fill_summary(rows)
        self.assertEqual(result['gross'], Decimal('-2.8532'))
        self.assertEqual(result['net'], Decimal('-2.9032'))
        self.assertEqual(fill_view(rows[0])['action'], '平多')
        self.assertEqual(rows[0].price, '75358.2')
        self.assertEqual(rows[0].contracts, '0.13')

    def test_opening_fee_and_rebate_included(self):
        store_fills(self.db, [fill(tradeId='open', subType='3', side='buy', fillPnl='0', fee='-0.04'),
                             fill(fee='0.01')], self.scope)
        result = fill_summary(self.db.query(ExecutionFill).all())
        self.assertEqual(result['fees_signed'], Decimal('-0.03'))
        self.assertEqual(result['net'], Decimal('-2.8832'))

    def test_missing_is_not_zero_and_can_be_enriched(self):
        store_fills(self.db, [fill(fillPnl='', fee='', feeCcy='')], self.scope)
        result = fill_summary(self.db.query(ExecutionFill).all())
        self.assertIsNone(result['net'])
        self.assertIsNone(result['gross'])
        self.assertEqual(result['fee_unknown'], 1)
        self.assertEqual(store_fills(self.db, [fill()], self.scope), 0)
        self.db.flush()
        self.assertEqual(fill_summary(self.db.query(ExecutionFill).all())['net'], Decimal('-2.9032'))

    def test_currency_not_mixed_and_conflicting_fill_rejected(self):
        store_fills(self.db, [fill(feeCcy='BTC')], self.scope)
        self.assertIsNone(fill_summary(self.db.query(ExecutionFill).all())['net'])
        with self.assertRaises(ValueError): store_fills(self.db, [fill(fillPx='1')], self.scope)
        self.db.rollback()
        with self.assertRaises(ValueError): store_fills(self.db, [fill(fillSz='nan')], self.scope)

    def test_accounts_are_isolated(self):
        store_fills(self.db, [fill()], self.scope)
        store_fills(self.db, [fill()], 'different-key')
        self.assertEqual(self.db.query(ExecutionFill).count(), 2)

    def test_sync_is_read_only_on_exchange_and_idempotent(self):
        client = Mock()
        def response(path, api, method, params):
            self.assertEqual(path, 'trade/fills-history')
            self.assertEqual(method, 'GET')
            return {'code':'0', 'data':[fill()]}
        client.request.side_effect = response
        with patch('ccxt.okx', return_value=client):
            self.assertEqual(sync_demo_fills(self.db)['added'], 1)
            self.assertEqual(sync_demo_fills(self.db)['added'], 0)
        self.assertEqual(self.db.query(ExecutionFill).count(), 1)
        client.create_order.assert_not_called()
        client.cancel_order.assert_not_called()
        self.assertTrue(client.session.verify)

    def test_live_and_missing_demo_credentials_rejected(self):
        self.cfg.okx_simulated = False
        self.db.commit()
        with patch('ccxt.okx') as client:
            with self.assertRaises(ValueError): sync_demo_fills(self.db)
            client.assert_not_called()
        self.cfg.okx_simulated = True
        self.cfg.okx_sim_secret_key_enc = ''
        self.db.commit()
        with patch('ccxt.okx') as client:
            with self.assertRaises(ValueError): sync_demo_fills(self.db)
            client.assert_not_called()

    def test_failed_or_truncated_sync_keeps_history(self):
        store_fills(self.db, [fill()], self.scope)
        self.db.commit()
        with patch('ccxt.okx'), patch('app.fill_ledger.paged', return_value=([fill(tradeId='new')], False)):
            with self.assertRaises(ValueError): sync_demo_fills(self.db)
        self.assertEqual(self.db.query(ExecutionFill).count(), 1)
        with patch('ccxt.okx'), patch('app.fill_ledger.paged', side_effect=RuntimeError('test-secret')):
            with self.assertRaises(RuntimeError): sync_demo_fills(self.db)
        self.assertEqual(self.db.query(ExecutionFill).count(), 1)

    def test_malformed_batch_is_atomic(self):
        client = Mock()
        with patch('ccxt.okx', return_value=client), patch('app.fill_ledger.paged',
                return_value=([fill(), fill(tradeId='bad', fillSz='')], True)):
            with self.assertRaises(ValueError): sync_demo_fills(self.db)
        self.assertEqual(self.db.query(ExecutionFill).count(), 0)

    def test_totals_cover_all_pages_not_legacy_estimates(self):
        from app.routers.pages import trades_page
        store_fills(self.db, [fill(tradeId=str(i), fee='-0.05', fillPnl='1') for i in range(51)], self.scope)
        strategy = Strategy(name='test', prompt_template='test', symbols_json='[]', enabled=False)
        self.db.add(strategy)
        self.db.flush()
        self.db.add(Trade(strategy_id=strategy.id, symbol='BTC-USDT-SWAP', side='long', action='close',
                          price=1, quantity=1, pnl=999999, fee=0))
        self.db.commit()
        request = Request({'type':'http', 'method':'GET', 'path':'/trades', 'headers':[]})
        response = trades_page(request, strategy_id=None, page=2, source='fills', db=self.db, period='all', page_size=50)
        self.assertEqual(response.context['total'], 51)
        self.assertEqual(len(response.context['fills']), 1)
        self.assertEqual(response.context['summary']['net'], Decimal('48.45'))
        self.assertEqual(response.context['summary']['gross'], Decimal(51))
        self.assertNotIn('999999', response.body.decode())
        self.assertIn('48.4500', response.body.decode())
        legacy = trades_page(request, strategy_id=None, page=1, source='legacy', db=self.db)
        self.assertIn('不参与盈亏统计', legacy.body.decode())

    def test_endpoint_errors_redacted(self):
        from app.routers.trading import sync_fills_now
        from fastapi import HTTPException
        with patch('app.fill_ledger.sync_demo_fills', side_effect=RuntimeError('test-secret')):
            with self.assertRaises(HTTPException) as error: sync_fills_now(self.db)
        self.assertEqual(error.exception.status_code, 502)
        self.assertNotIn('test-secret', str(error.exception.detail))

    def test_new_table_preserves_old_records(self):
        ExecutionFill.__table__.drop(self.engine)
        strategy = Strategy(name='preserve', prompt_template='test', symbols_json='[]', enabled=False)
        self.db.add(strategy)
        self.db.flush()
        old = Trade(strategy_id=strategy.id, symbol='BTC-USDT-SWAP', side='long', action='open', price=100, quantity=0.13, status='filled', pnl=None)
        self.db.add(old)
        self.db.commit()
        Base.metadata.create_all(self.engine)
        self.assertEqual(self.db.query(ExecutionFill).count(), 0)
        self.assertEqual(self.db.query(Trade).one().status, 'filled')
        self.assertEqual(self.db.query(Trade).one().quantity, 0.13)

    def test_account_switch_during_sync_cancels_write(self):
        client = Mock()
        original = self.scope
        def response(*args):
            cfg = self.db.query(SystemConfig).first()
            cfg.okx_sim_api_key_enc = encrypt_value('new-demo-key')
            self.db.commit()
            return ([fill()], True)
        with patch('ccxt.okx', return_value=client), patch('app.fill_ledger.paged', side_effect=response):
            with self.assertRaises(ValueError): sync_demo_fills(self.db)
        self.assertEqual(self.db.query(ExecutionFill).count(), 0)
        self.assertNotEqual(account_key(self.db.query(SystemConfig).first()), original)

    def test_strategy_filter_does_not_claim_unassigned_fills(self):
        from app.routers.pages import trades_page
        store_fills(self.db, [fill()], self.scope)
        self.db.commit()
        response = trades_page(Request({'type':'http','method':'GET','path':'/trades','headers':[]}),
                               strategy_id=123, page=1, source='fills', db=self.db)
        self.assertEqual(response.context['total'], 0)
        self.assertIsNone(response.context['summary'])
        self.assertIn('尚未可靠归属策略', response.context['ledger_error'])
