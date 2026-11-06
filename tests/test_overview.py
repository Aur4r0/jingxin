"""界面回归测试；不启动调度器或调用交易所。"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app.routers.pages import templates


class OverviewTests(unittest.TestCase):
    def test_login_required(self):
        client = TestClient(app)
        response = client.get('/overview', follow_redirects=False)
        self.assertEqual(response.status_code, 303)

    def test_populated_template(self):
        html = templates.get_template('overview.html').render(
            request=SimpleNamespace(), active_page='overview',
            latest=SimpleNamespace(total_equity=10248.6, available_balance=9824.2, timestamp=datetime(2026, 11, 5)),
            positions=[], strategy_count=3, enabled_count=2, pnl=0,
            logs=[], strategy_names={}, position_time=None,
            chart_data=[{'time': '2026-11-05T00:00:00Z', 'equity': 10248.6}],
        )
        self.assertIn('10,248.60', html)
        self.assertIn('equityChart', html)
        self.assertIn('monitorChartData', html)
        self.assertIn('/static/monitor.js', html)


if __name__ == '__main__':
    unittest.main()
