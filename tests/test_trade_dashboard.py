import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from app.models import Base, SystemConfig, ExecutionFill, get_db
from app.fill_ledger import store_fills, account_key
from app.config import encrypt_value
from app.trade_dashboard import date_range, dashboard, accumulate, public_stats, money, tone


def raw_fill(identifier, ts, symbol='BTC-USDT-SWAP', pnl='1', fee='-0.1', order=None):
    return dict(instId=symbol, ordId=order or 'order-'+identifier, tradeId=identifier,
                side='sell', posSide='long', subType='5', fillPx='70000', fillSz='0.1',
                fillPnl=pnl, fee=fee, feeCcy='USDT', ts=str(int(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()*1000)))


class DateTests(unittest.TestCase):
    def test_today_yesterday_cross_month(self):
        now = datetime(2026,11,1,0,10,tzinfo=timezone.utc)
        today = date_range('today',now=now)
        self.assertEqual(today.bounds, (datetime(2026,10,31,16), datetime(2026,11,1,16)))
        yesterday = date_range('yesterday',now=now)
        self.assertEqual(yesterday.start,date(2026,10,31))
        self.assertEqual(yesterday.bounds[0],datetime(2026,10,30,16))
        self.assertEqual(date_range('7d',now=now).start,date(2026,10,26))
        self.assertEqual(date_range('30d',now=now).start,date(2026,10,3))

    def test_custom_includes_end_date_and_leap_day(self):
        selected = date_range('custom','2024-02-29','2024-03-01')
        self.assertEqual(selected.bounds,(datetime(2024,2,28,16),datetime(2024,3,1,16)))
        self.assertEqual(date_range('all').bounds,(None,None))
        for start,end in [('2026-11-02','2026-11-01'),('bad','2026-11-01'),('',''),('2020-01-01','2026-11-01'),('0001-01-01','0001-01-02')]:
            with self.assertRaises(ValueError): date_range('custom',start,end)
        with self.assertRaises(ValueError): date_range('invalid')

    def test_fee_sign_missing_and_zero(self):
        row=lambda pnl,fee,ccy='USDT',oid='1': SimpleNamespace(realized_pnl=pnl,fee_signed=fee,fee_currency=ccy,order_id=oid)
        result=accumulate([row('0','-1'),row('-2','0.5')])
        self.assertEqual(result['cost'],Decimal(1))
        self.assertEqual(result['rebate'],Decimal('0.5'))
        self.assertEqual(result['fees_cost'],Decimal('0.5'))
        self.assertEqual(result['net'],Decimal('-2.5'))
        self.assertEqual(result['count'],2)
        self.assertEqual(result['orders'],1)
        missing=accumulate([row(None,None),row('0','1','BTC')])
        self.assertEqual(missing['unknown'],2)
        self.assertIsNone(missing['gross'])
        self.assertIsNone(missing['net'])
        self.assertIsNone(accumulate([])['net'])
        zero=accumulate([row('0','0')])
        self.assertEqual(zero['net'],Decimal(0))
        self.assertEqual(tone(0),'neutral')
        self.assertEqual(money(Decimal('-0.00001')),'0.0000')


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        cfg=SystemConfig(id=1,okx_simulated=True,okx_sim_api_key_enc=encrypt_value('dashboard-test-key'),
            okx_sim_secret_key_enc=encrypt_value('test-secret'),okx_sim_passphrase_enc=encrypt_value('test-pass'))
        self.db.add(cfg);self.db.commit();self.scope=account_key(cfg)

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def add(self, rows):
        store_fills(self.db, rows, self.scope);self.db.commit()

    def test_boundaries_pair_filter_and_chart_match(self):
        self.add([raw_fill('before','2026-10-31T15:59:59'), raw_fill('start','2026-10-31T16:00:00'),
                  raw_fill('end','2026-11-01T15:59:59'),raw_fill('after','2026-11-01T16:00:00'),
                  raw_fill('eth','2026-11-01T00:00:00','ETH-USDT-SWAP',pnl='20')])
        view=dashboard(self.db,'custom','2026-11-01','2026-11-01','BTC-USDT-SWAP')
        self.assertEqual(view['total'],2)
        self.assertEqual(view['summary']['net'],Decimal('1.8'))
        self.assertEqual(view['chart'],[dict(date='2026-11-01',count=2,unknown=0,gross='2',fees_cost='0.2',net='1.8')])
        self.assertEqual({x['record'].fill_id for x in view['fills']},{'start','end'})
        self.assertIn('ETH-USDT-SWAP',view['symbols'])

    def test_paging_does_not_change_totals_and_links_keep_filters(self):
        self.add([raw_fill(str(i),'2026-11-01T01:00:00',order='same-order') for i in range(25)])
        first=dashboard(self.db,'custom','2026-11-01','2026-11-01','BTC-USDT-SWAP')
        second=dashboard(self.db,'custom','2026-11-01','2026-11-01','BTC-USDT-SWAP',page=2)
        self.assertEqual(len(first['fills']),10)
        self.assertEqual(len(second['fills']),10)
        self.assertEqual(first['summary'],second['summary'])
        self.assertEqual(first['chart'],second['chart'])
        self.assertEqual(second['summary']['orders'],1)
        self.assertEqual(second['summary']['net'],Decimal('22.5'))
        for expected in ['period=custom','start_date=2026-11-01','end_date=2026-11-01','symbol=BTC-USDT-SWAP','page_size=10','page=3']:
            self.assertIn(expected,second['next_url'])
        self.assertEqual(len(dashboard(self.db,'all',page_size=20)['fills']),20)
        self.assertEqual(len(dashboard(self.db,'all',page_size=50)['fills']),25)
        self.assertEqual(dashboard(self.db,'all',page=99)['page'],3)
        with self.assertRaises(ValueError):dashboard(self.db,'all',page_size=100)

    def test_missing_days_not_filled_with_zero(self):
        self.add([raw_fill('zero','2026-11-01T01:00:00',pnl='0',fee='0'),
                  raw_fill('unknown','2026-11-02T01:00:00',pnl='',fee='')])
        view=dashboard(self.db,'custom','2026-11-01','2026-11-03')
        self.assertEqual(view['chart'][0]['net'],'0')
        self.assertEqual(view['chart'][1]['count'],1)
        self.assertIsNone(view['chart'][1]['net'])
        self.assertEqual(view['chart'][2]['count'],0)
        self.assertIsNone(view['chart'][2]['net'])
        self.assertIsNone(view['summary']['net'])
        self.assertIn('未保存',view['coverage_warning'])

    def test_empty_and_other_accounts_not_zero_or_mixed(self):
        view=dashboard(self.db,'all')
        self.assertEqual(view['total'],0)
        self.assertIsNone(view['summary']['net'])
        self.assertIsNone(view['known_range'])
        store_fills(self.db,[raw_fill('other','2026-11-01T01:00:00')],'another-account');self.db.commit()
        self.assertEqual(dashboard(self.db,'all')['total'],0)

    def test_api_and_page_same_read_only_data(self):
        from app.routers.pages import trades_page
        from app.routers.trading import trade_statistics
        self.add([raw_fill('a','2026-11-01T01:00:00')])
        with patch('ccxt.okx') as network:
            stats=trade_statistics(period='custom',start_date='2026-11-01',end_date='2026-11-01',symbol='',db=self.db)
            response=trades_page(Request({'type':'http','method':'GET','path':'/trades','headers':[]}),
                page=1,db=self.db,period='custom',start_date='2026-11-01',end_date='2026-11-01')
            network.assert_not_called()
        self.assertEqual(stats,public_stats(response.context))
        html=response.body.decode()
        self.assertIn('每页',html)
        self.assertIn('id="tradeDetails"',html)
        self.assertIn('净交易盈亏',html)
        self.assertIn('完整订单 ID',html)
        self.assertIn('手续费返佣',html)
        self.assertEqual(stats['summary']['net'],'0.9')
        self.assertEqual(stats['summary']['orders'],1)
        self.assertEqual(self.db.query(ExecutionFill).count(),1)

    def test_api_rejects_invalid_dates(self):
        from app.routers.trading import trade_statistics
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            trade_statistics(period='custom',start_date='2026-11-02',end_date='2026-11-01',symbol='',db=self.db)
        self.assertEqual(error.exception.status_code,400)

    def test_sync_time_uses_last_success_beijing_not_failed_check(self):
        from app.routers.pages import trades_page
        status={'fills':{'ok':False,'last_success':'2026-11-01T01:15:00+00:00','checked_at':'2026-11-01T02:00:00+00:00','message':'同步失败'}}
        with patch('app.runtime_status.snapshot',return_value=status):
            response=trades_page(Request({'type':'http','method':'GET','path':'/trades','headers':[]}),page=1,db=self.db)
        self.assertEqual(response.context['sync_time'],'11-01 09:15')
        self.assertIn('同步失败',response.body.decode())

    def test_theme_mobile_and_keyboard_chart_contract(self):
        root=Path(__file__).resolve().parents[1]
        css=(root/'static/trades.css').read_text()
        js=(root/'static/trades.js').read_text()
        self.assertIn('html[data-theme="light"]',css)
        self.assertIn('@media(max-width:700px)',css)
        self.assertIn('overflow-wrap:anywhere',css)
        self.assertIn("addEventListener('focus'",js)
        self.assertIn("addEventListener('mouseenter'",js)
        self.assertIn('point.net === null',js)
        self.assertIn('sessionStorage',js)
