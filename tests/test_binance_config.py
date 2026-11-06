import unittest
from unittest.mock import MagicMock, patch
from app.binance_connection import build_client, read_account
from app.routers.system import BinanceConnectionTest, test_binance_connection
from fastapi import HTTPException

class BinanceTests(unittest.TestCase):
    def test_hosts_separated(self):
        demo=build_client('demo','secret',True,'')
        live=build_client('live','secret',False,'')
        self.assertTrue(all('demo-fapi.binance.com' in url for key,url in demo.urls['api'].items() if key.startswith('fapi')))
        self.assertIn('https://fapi.binance.com/',live.urls['api']['fapiPrivateV2'])
        self.assertTrue(demo.session.verify)
        demo.session.close();live.session.close()
    def test_read_only_call(self):
        client=MagicMock()
        with patch('app.binance_connection.build_client',return_value=client):
            read_account('key','secret',True,'')
        client.fapiPrivateV2GetAccount.assert_called_once_with()
        client.create_order.assert_not_called()
        client.session.close.assert_called_once()
    def test_demo_never_falls_back_to_live(self):
        cfg=MagicMock(binance_sim_api_key_enc='',binance_sim_secret_key_enc='',binance_live_api_key_enc='live',binance_live_secret_key_enc='secret')
        db=MagicMock();db.query.return_value.first.return_value=cfg
        with self.assertRaises(HTTPException) as error:
            test_binance_connection(BinanceConnectionTest(environment='sim'),db)
        self.assertEqual(error.exception.status_code,400)
