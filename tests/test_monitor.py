from helpers import authenticated_client
"""第三批只读页面和前端脚本检查。"""
import subprocess
import unittest
from fastapi.testclient import TestClient
from app.main import app
from test_phase_two import Scripts


class MonitorTests(unittest.TestCase):
    def test_pages_keep_monitor_controls_outside_content(self):
        client=authenticated_client()
        for path in ['/overview','/positions','/logs?strategy_id=1&page=2','/trades?page=2']:
            response=client.get(path)
            self.assertEqual(response.status_code,200)
            html=response.text
            self.assertEqual(html.count('id="monitorContent"'),1)
            self.assertLess(html.index('id="monitorStatus"'),html.index('id="monitorContent"'))
            self.assertIn('/static/monitor.js?v=20261106-1',html)
            self.assertNotIn('setInterval(refreshPositionsLive',html)
            parser=Scripts();parser.feed(html)
            # application/json 数据块由 DOM 单独读取，不作为代码检查。
            if path=='/positions':
                parser.code=[code for code in parser.code if code.strip()!='[]']
            result=subprocess.run(['node','--check'],input='\n'.join(parser.code),text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_frontend_monitor_failure_and_background_pause(self):
        result=subprocess.run(['node','tests/monitor.test.cjs'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
