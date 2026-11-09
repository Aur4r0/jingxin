from helpers import authenticated_client
"""第二批界面回归：不创建策略或提交订单。"""
import unittest
import subprocess
from types import SimpleNamespace
from datetime import datetime
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from app.main import app
from app.routers.pages import templates, _fmt_bj_time, _action_label, _action_badge_class


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside=False; self.code=[]
    def handle_starttag(self, tag, attrs):
        if tag=='script': self.inside='src' not in dict(attrs)
    def handle_endtag(self,tag):
        if tag=='script': self.inside=False
    def handle_data(self,data):
        if self.inside: self.code.append(data)


class PhaseTwoTests(unittest.TestCase):
    def test_new_strategy_and_theme(self):
        client=authenticated_client()
        response=client.get('/strategies/new')
        self.assertEqual(response.status_code,200)
        for title in ['基本信息','交易设置','决策设置','高级设置','beforeunload','strategyFingerprint']:
            self.assertIn(title,response.text)
        self.assertIn('name="enabled" type="hidden" value=""',response.text)
        self.assertNotIn('bi-sun"></i> 日间',response.text)
        parser=Scripts();parser.feed(response.text)
        result=subprocess.run(['node','--check'],input='\n'.join(parser.code),text=True,encoding='utf-8',capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_edit_preserves_existing_values(self):
        from unittest.mock import MagicMock
        from app.models import Strategy
        from app.routers.pages import strategy_edit_page
        from starlette.requests import Request
        strategy=Strategy(id=7,name='已有规则策略',enabled=True,use_ai=False,position_usdt=275,
            leverage=2,interval_minutes=30,prompt_template='保留原提示词',symbols_json='["BTC-USDT-SWAP"]',
            scan_enabled=False,scan_exclude_symbols='[]')
        db=MagicMock();db.query.return_value.filter.return_value.first.return_value=strategy
        response=strategy_edit_page(7,Request({'type':'http','method':'GET','path':'/strategies/7/edit','headers':[]}),db)
        view=response.context['strategy']
        self.assertEqual(view.position_usdt,275)
        self.assertFalse(view.use_ai)
        self.assertTrue(view.enabled)
        html=response.body.decode()
        self.assertIn('name="enabled" type="hidden" value="true"',html)
        self.assertIn('value="275"',html)
        self.assertIn('规则计算',html)

    def test_log_content_is_escaped_and_folded(self):
        log=SimpleNamespace(id=99,strategy_id=1,symbol='BTC-USDT-SWAP',created_at=datetime(2026,11,5),parsed_action='hold',parsed_confidence=80,order_placed=False,order_id='',parsed_reasoning='等待',error_message='',prompt_sent='<script>unsafe</script>',ai_raw_response='{"action":"hold"}')
        html=templates.get_template('logs.html').render(request=SimpleNamespace(),active_page='logs',strategies=[],filter_strategy_id=None,logs=[log],strategy_names={1:'测试策略'},page=1,total_pages=1,fmt_bj_time=_fmt_bj_time,action_label=_action_label,action_badge_class=_action_badge_class)
        self.assertIn('class="log-details"',html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',html)
        self.assertIn('非胜率',html)
        self.assertIn('未记录下单',html)
        self.assertIn('data-copy-target="logPrompt99"',html)

if __name__=='__main__':unittest.main()
