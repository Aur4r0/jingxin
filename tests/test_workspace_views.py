"""统一工作台界面回归；只使用隔离数据库，不启动调度器。"""
import unittest
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.models import Base, Strategy, StrategyLog, Position, EquitySnapshot, SystemConfig, get_db
from app.config import encrypt_value, settings
from app.main import app
from app.ui_views import ui_number, ui_tone, position_pnl, execution_state
from helpers import authenticated_client


class FormFields(HTMLParser):
    def __init__(self):super().__init__();self.inputs={};self.forms=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='input' and a.get('name'):self.inputs[a['name']]=a
        if tag=='form':self.forms.append(a)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        # 每个测试独立计算登录限流，不改变应用的真实限制。
        from app.main import AuthRequiredMiddleware
        AuthRequiredMiddleware.login_attempts.clear()
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.db=sessionmaker(bind=self.engine)()
        cfg=SystemConfig(id=1,okx_simulated=True,okx_sim_api_key_enc=encrypt_value('test-only-key'),
            okx_sim_secret_key_enc=encrypt_value('test-only-secret'),okx_sim_passphrase_enc=encrypt_value('test-only-pass'))
        s=Strategy(id=1,name='测试策略 <script>not-code</script>',enabled=True,use_ai=False,
                   prompt_template='保持原文 {symbol} <tag>',symbols_json='["BTC-USDT-SWAP","ETH-USDT-SWAP"]',
                   interval_minutes=30,position_usdt=275,leverage=2,scan_enabled=False)
        self.db.add_all([cfg,s]);self.db.flush()
        for i in range(6):self.db.add(Position(symbol=f'COIN{i}-USDT-SWAP',side='long',size=0.13,
                                             avg_price=100,unrealized_pnl=1,margin=2,leverage=2,tp_price=None,sl_price=None))
        for i in range(25):self.db.add(StrategyLog(strategy_id=1,symbol='BTC-USDT-SWAP',parsed_action='hold',
            parsed_reasoning='等待信号',prompt_sent='<script>unsafe</script>',ai_raw_response='{"action":"hold"}'))
        self.db.add(EquitySnapshot(total_equity=10248.6,available_balance=9800,timestamp=datetime(2026,11,9)))
        self.db.commit()
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=authenticated_client()
    def tearDown(self):
        app.dependency_overrides.pop(get_db,None);self.db.close();self.engine.dispose()

    def test_overview_limits_summary_and_shows_source(self):
        html=self.client.get('/overview').text
        self.assertIn('10,248.60',html)
        self.assertIn('COIN4-USDT-SWAP',html)
        self.assertNotIn('COIN5-USDT-SWAP',html)
        self.assertIn('账户权益曲线',html)
        self.assertIn('切换账户',html)
        self.assertIn('查看全部',html)

    def test_positions_never_claim_protection_confirmed(self):
        html=self.client.get('/positions').text
        self.assertIn('待核实',html)
        self.assertIn('无法证明算法单当前有效',html)
        self.assertNotIn('已保护',html)
        self.assertIn('confirmAction',html)
        self.assertIn("'/positions/close',{symbol,side}",html)
        self.assertIn('合约张数',html)
        self.assertEqual(html.count('/static/monitor.js?'),1)

    def test_strategy_display_does_not_change_values_or_prompt(self):
        before=self.db.get(Strategy,1)
        before_values=(before.name,before.enabled,before.prompt_template,before.position_usdt,before.interval_minutes,before.leverage)
        html=self.client.get('/strategies/1/edit').text
        form=FormFields();form.feed(html)
        self.assertEqual(form.inputs['position_usdt']['value'],'275.0')
        self.assertEqual(form.inputs['enabled']['value'],'true')
        self.assertEqual(form.inputs['interval_minutes']['value'],'30')
        self.assertIn('保持原文 {symbol} &lt;tag&gt;',html)
        self.assertIn('beforeunload',html)
        self.assertIn('确认保存',html)
        self.db.expire_all();after=self.db.get(Strategy,1)
        self.assertEqual(before_values,(after.name,after.enabled,after.prompt_template,after.position_usdt,after.interval_minutes,after.leverage))

    def test_strategy_list_mode_status_and_recent_result(self):
        html=self.client.get('/strategies').text
        self.assertIn('规则决策',html)
        self.assertIn('持有 · 未下单',html)
        self.assertIn('data-enabled="true"',html)
        self.assertIn('立即执行策略',html)
        self.assertIn('&lt;script&gt;not-code&lt;/script&gt;',html)
        self.assertNotIn('<script>not-code</script>',html)

    def test_logs_pagination_and_safe_details(self):
        first=self.client.get('/logs').text
        second=self.client.get('/logs?strategy_id=1&page=2&page_size=10').text
        self.assertEqual(first.count('class="jx-log-record"'),10)
        self.assertEqual(second.count('class="jx-log-record"'),10)
        self.assertIn('page_size=10',second)
        self.assertIn('strategy_id=1',second)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',first)
        self.assertIn('复制提示词',first)
        self.assertEqual(self.client.get('/logs?page_size=50').text.count('class="jx-log-record"'),25)

    def test_settings_order_and_no_secret_values(self):
        html=self.client.get('/settings').text
        sections=['data-section="account"','data-section="ai"','data-section="notification"','data-section="binance"','data-section="advanced"']
        self.assertEqual([html.index(x) for x in sections],sorted(html.index(x) for x in sections))
        for secret in ['test-only-key','test-only-secret','test-only-pass']:
            self.assertNotIn(secret,html)
        self.assertIn('测试已保存的交易账户',html)
        self.assertIn('使用当前输入发送消息',html)
        self.assertIn('本版本尚未接入币安策略执行',html)

    def test_read_pages_do_not_call_exchange_or_write_records(self):
        counts=lambda:tuple(self.db.query(model).count() for model in [Strategy,StrategyLog,Position,EquitySnapshot,SystemConfig])
        before=counts()
        with patch('ccxt.okx') as ex,patch('app.engine.run_strategy') as execute:
            for page in ['/overview','/positions','/strategies','/strategies/new','/strategies/1/edit','/logs','/settings','/prompt-templates','/trades']:
                self.assertEqual(self.client.get(page).status_code,200,page)
            ex.assert_not_called();execute.assert_not_called()
        self.assertEqual(before,counts())

    def test_authentication_still_required(self):
        client=TestClient(app)
        for url in ['/overview','/positions','/strategies','/settings','/logs']:
            self.assertEqual(client.get(url,follow_redirects=False).status_code,303)
        self.assertEqual(client.post('/api/positions/close',json={'symbol':'BTC-USDT-SWAP','side':'long'}).status_code,401)
        self.assertEqual(client.get('/api/system/config').status_code,401)
        html=client.get('/login').text
        self.assertIn('autocomplete="current-password"',html)
        self.assertIn('passwordToggle',html)
        self.assertNotIn(settings.app_password_hash,html)

    def test_history_keeps_separate_styles_and_layout(self):
        html=self.client.get('/trades').text
        self.assertIn('/static/trades.css',html)
        self.assertNotIn('/static/workspace.css',html)
        self.assertIn('净交易盈亏',html)

    def test_null_numbers_and_execution_states(self):
        self.assertEqual(ui_number(None),'—')
        self.assertEqual(ui_number(float('nan')),'—')
        self.assertEqual(ui_number(0), '0.00')
        self.assertIsNone(position_pnl([]))
        self.assertIsNone(position_pnl([SimpleNamespace(unrealized_pnl=None)]))
        self.assertEqual(ui_tone(None),'neutral')
        log=SimpleNamespace(order_placed=True,error_message='保护单未确认',parsed_action='long',parsed_reasoning='')
        self.assertEqual(execution_state(log)['label'],'已提交 · 待核对')
        log.order_placed=False;log.error_message='行情无效，本轮已跳过'
        self.assertEqual(execution_state(log)['label'],'本轮跳过')

    def test_real_login_validation_without_bypass(self):
        from app.security import hash_password
        with patch('app.config.settings.app_password_hash',hash_password('fixture-password-only')):
            client=TestClient(app)
            bad=client.post('/login',data={'username':settings.app_username,'password':'wrong'},follow_redirects=False)
            self.assertEqual(bad.status_code,400)
            good=client.post('/login',data={'username':settings.app_username,'password':'fixture-password-only'},follow_redirects=False)
            self.assertEqual(good.status_code,303)
            self.assertEqual(client.get('/overview').status_code,200)

    def test_assets_scope_and_no_secret_storage(self):
        root=Path(__file__).resolve().parents[1]
        css=(root/'static/workspace.css').read_text();js=(root/'static/workspace.js').read_text()
        self.assertIn('html[data-theme="light"] .jx',css)
        self.assertIn('@media(max-width:700px)',css)
        self.assertNotIn('localStorage.setItem',js)
        self.assertNotIn('sessionStorage.setItem',js)
        monitor=(root/'static/monitor.js').read_text()
        self.assertIn('details.jx-log-record[open]',monitor)
        self.assertIn('details.jx-position-record[open]',monitor)

    def test_auto_refresh_protects_reading_and_actions(self):
        import subprocess
        result=subprocess.run(['node','tests/workspace-monitor.test.cjs'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_inline_scripts_parse(self):
        import subprocess
        from test_phase_two import Scripts
        for path in ['/login','/overview','/positions','/strategies','/strategies/new','/strategies/1/edit','/logs','/settings','/prompt-templates']:
            html=self.client.get(path).text
            parser=Scripts();parser.feed(html)
            result=subprocess.run(['node','--check'],input='\n'.join(parser.code),text=True,capture_output=True)
            self.assertEqual(result.returncode,0,path+result.stderr)

    def test_blank_strategy_filter_is_all_and_invalid_is_reported(self):
        response=self.client.get('/logs?strategy_id=&page_size=20')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.text.count('class="jx-log-record"'),20)
        self.assertEqual(self.client.get('/logs?strategy_id=not-an-id').status_code,400)
