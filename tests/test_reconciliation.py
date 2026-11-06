import unittest
from decimal import Decimal
from unittest.mock import Mock
from app.contracts import Contract, inst_id
from app.reconciliation import collect, paged, read, summarize_fills, STATUS

SPEC = {'instId': 'BTC-USDT-SWAP', 'ctType': 'linear', 'settleCcy': 'USDT',
        'ctValCcy': 'BTC', 'ctVal': '0.01', 'ctMult': '1', 'lotSz': '0.01', 'minSz': '0.01'}


class ReconciliationTests(unittest.TestCase):
    def test_symbol_and_units(self):
        self.assertEqual(inst_id('BTC/USDT:USDT'), inst_id('BTC-USDT-SWAP'))
        with self.assertRaises(ValueError): inst_id('BTC/USD:BTC')
        c = Contract.from_okx(SPEC)
        units = c.amounts('0.13', '75358.2')
        self.assertEqual(Decimal(units['base_quantity']), Decimal('0.0013'))
        self.assertEqual(Decimal(units['notional_usdt']), Decimal('97.96566'))

    def test_budget_accounts_for_old_position_and_pending(self):
        c = Contract.from_okx(SPEC)
        self.assertEqual(c.remaining_contracts('100', '75358.2', '0.12', '0'), Decimal('0.01'))
        self.assertEqual(c.remaining_contracts('100', '75358.2', '0.12', '0.01'), Decimal('0'))
        self.assertEqual(c.remaining_contracts('100', '75358.2', '0.25', '0'), Decimal('0'))
        with self.assertRaises(ValueError): c.remaining_contracts('100', 'NaN', '0', '0')
        with self.assertRaises(ValueError): Contract.from_okx(dict(SPEC, ctVal=''))
        with self.assertRaises(ValueError): Contract.from_okx(dict(SPEC, ctValCcy='USD'))

    def test_fills_deduplicate_and_preserve_fee_currency(self):
        f = dict(instId='BTC-USDT-SWAP', ordId='2', tradeId='3', fillSz='0.13', fillPx='75358.2',
                 fillPnl='-2.8532', fee='-0.05', feeCcy='USDT')
        unique, totals = summarize_fills([f, f])
        self.assertEqual(len(unique), 1)
        self.assertEqual(totals[0]['net_pnl_usdt_in_window'], '-2.9032')
        self.assertEqual(totals[0]['fill_average_in_window'], '75358.2')
        self.assertIsNone(summarize_fills([dict(f, feeCcy='BTC')])[1][0]['net_pnl_usdt_in_window'])
        self.assertIsNone(summarize_fills([dict(f, fee='')])[1][0]['net_pnl_usdt_in_window'])
        self.assertIsNone(summarize_fills([dict(f, fillPnl='')])[1][0]['realized_pnl_in_window'])

    def test_only_read_and_bounded_pagination(self):
        client = Mock()
        with self.assertRaises(ValueError): read(client, 'trade/cancel-order', {})
        client.request.assert_not_called()
        client.request.return_value = {'code':'0', 'data':[{'billId':str(i)} for i in range(100)]}
        rows, complete = paged(client, 'trade/fills-history', {}, 'billId', 2)
        self.assertFalse(complete)
        self.assertEqual(len(rows), 200)
        self.assertEqual(client.request.call_args.args[2], 'GET')
        self.assertEqual(client.request.call_args.args[3]['after'], '99')

    def test_residual_protection_and_unmatched_fill(self):
        client = Mock()
        def response(path, api, method, params):
            self.assertEqual(method, 'GET')
            data = []
            if path == 'public/instruments': data = [SPEC]
            if path == 'account/positions': data = [{'posSide':'long', 'pos':'0.12', 'markPx':'75358.2'}]
            if path == 'trade/orders-algo-pending' and params['ordType']=='conditional':
                data = [{'algoId':'4', 'posSide':'long', 'side':'sell', 'sz':'0.13'}]
            if path == 'trade/fills-history':
                data = [dict(instId='BTC-USDT-SWAP', ordId='2', tradeId='3', fillSz='0.13', fillPx='75358.2', fillPnl='-2.8532', fee='-0.05', feeCcy='USDT')]
            if path == 'trade/order': data = [{'ordId':'1', 'state':'partially_filled'}]
            return {'code':'0', 'data':data}
        client.request.side_effect = response
        report = collect(client, 'BTC-USDT-SWAP', [{'order_id':'1'}], 0)
        self.assertEqual(report['orders'][0]['status'], 'partially_filled')
        self.assertEqual(len(report['fills_without_local_order']), 1)
        self.assertTrue(any('超过' in warning for warning in report['warnings']))
        self.assertEqual(STATUS.get('unrecognized', 'unknown'), 'unknown')

    def test_failures_not_reported_as_empty_success_or_leak(self):
        client = Mock()
        client.request.side_effect = RuntimeError('secret-token')
        report = collect(client, 'BTC-USDT-SWAP', [{'order_id':'1'}], 0)
        self.assertFalse(report['coverage']['positions'])
        self.assertEqual(report['orders'][0]['status'], 'unknown')
        self.assertNotIn('secret-token', str(report))


class ReadOnlyConfigurationTests(unittest.TestCase):
    def test_demo_credentials_only_and_no_database_mutation(self):
        import importlib.util
        from pathlib import Path
        import sqlite3
        import tempfile
        from cryptography.fernet import Fernet
        spec = importlib.util.spec_from_file_location('reconcile_cli', Path(__file__).resolve().parents[1] / 'scripts/reconcile_demo.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            database, env = base / 'test.db', base / '.env'
            key = Fernet.generate_key()
            cipher = Fernet(key)
            env.write_text('ENCRYPTION_KEY=' + key.decode())
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE system_config (okx_simulated integer, okx_sim_api_key_enc text, okx_sim_secret_key_enc text, okx_sim_passphrase_enc text, okx_proxy text)')
                db.execute('INSERT INTO system_config VALUES (1,?,?,?,?)', (*[cipher.encrypt(x.encode()).decode() for x in ('test-key','test-secret','test-pass')], ''))
                db.execute('CREATE TABLE trades (id integer,strategy_id integer,symbol text,order_id text,status text,price real,quantity real,pnl real,fee real,tp_order_id text,sl_order_id text)')
                db.execute('CREATE TABLE strategies (enabled integer)')
                db.execute('INSERT INTO strategies VALUES (1)')
            before = database.read_bytes()
            credentials, _, _, enabled = cli.load_local(database, env, 'BTC-USDT-SWAP')
            self.assertEqual(credentials, ['test-key','test-secret','test-pass'])
            self.assertEqual(enabled, 1)
            self.assertEqual(before, database.read_bytes())
            with sqlite3.connect(database) as db:
                db.execute('UPDATE system_config SET okx_simulated=0')
            with self.assertRaises(ValueError): cli.load_local(database, env, 'BTC-USDT-SWAP')
            with sqlite3.connect(database) as db:
                db.execute("UPDATE system_config SET okx_simulated=1, okx_sim_secret_key_enc=''")
            with self.assertRaises(ValueError): cli.load_local(database, env, 'BTC-USDT-SWAP')
