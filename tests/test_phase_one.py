from helpers import authenticated_client
"""只读页面回归，不启动调度器或执行交易。"""
import unittest
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from app.main import app


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None
        self.nested = False
        self.navigation = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.nested |= self.current is not None
            self.current = {'section': attrs.get('data-section'), 'fields': []}
            self.forms.append(self.current)
        if tag in ('input', 'select') and self.current is not None:
            self.current['fields'].append(attrs.get('name'))
        if tag == 'a' and 'pp-navlink' in attrs.get('class', ''):
            self.navigation += 1
    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


class PhaseOneTests(unittest.TestCase):
    def setUp(self):
        self.client = authenticated_client()
    def test_settings_independent_forms(self):
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        page = Structure(); page.feed(response.text)
        self.assertFalse(page.nested)
        self.assertEqual(page.navigation, 5)
        forms = {f['section']: f['fields'] for f in page.forms}
        self.assertEqual(set(forms), {'account','ai','notification','advanced','binance'})
        self.assertNotIn('ai_default_model', forms['account'])
        self.assertIn('tg_chat_id', forms['notification'])
        self.assertEqual(forms['advanced'], ['okx_proxy'])
    def test_grouped_navigation(self):
        for path, active in [('/strategies','策略'),('/prompt-templates','策略'),('/positions','持仓与交易'),('/trades','持仓与交易')]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('pp-section-tabs', response.text)
            self.assertIn(f'aria-label="{active}"', response.text)
    def test_confirmation_assets(self):
        response = self.client.get('/strategies')
        self.assertIn('confirmAction', response.text)
        self.assertIn('/static/interactions.js', response.text)

if __name__ == '__main__':
    unittest.main()
