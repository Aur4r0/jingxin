import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('windows_bootstrap',Path(__file__).resolve().parents[1]/'scripts/windows_bootstrap.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class WindowsBootstrapTests(unittest.TestCase):
    def test_rejects_non_windows(self):
        with patch.object(module.sys,'platform','darwin'):
            with self.assertRaises(RuntimeError):module.main()
    def test_fresh_flow_does_not_start_service(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'ROOT',Path(folder)),patch.object(module.sys,'platform','win32'),patch.object(module.sys,'version_info',(3,12)),patch.object(module,'run') as run,redirect_stdout(StringIO()) as output:
            module.main()
            commands=[call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands),4)
            self.assertTrue(any('scripts/setup.py' in cmd for cmd in commands))
            self.assertFalse(any('run.py' in cmd for cmd in commands))
            self.assertIn('配置完成',output.getvalue())
    def test_existing_incompatible_environment_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'ROOT',Path(folder)),patch.object(module.sys,'platform','win32'),patch.object(module.sys,'version_info',(3,12)):
            Path(folder,'.venv').mkdir()
            with self.assertRaises(RuntimeError):module.main()
            self.assertTrue(Path(folder,'.venv').is_dir())
