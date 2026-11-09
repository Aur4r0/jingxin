from contextlib import closing, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    def make_backup(self, folder):
        folder.mkdir()
        key = Fernet.generate_key()
        (folder / '.env').write_text(
            'APP_USERNAME=test-admin\nAPP_PASSWORD_HASH=test-only-placeholder\n'
            'APP_SESSION_SECRET=test-only-session-secret-at-least-32-characters\n'
            'ENCRYPTION_KEY=' + key.decode() + '\n', encoding='utf-8')
        (folder / '.env').chmod(0o600)
        # SQLite 的事务上下文不会关闭连接，必须显式释放文件句柄。
        with closing(sqlite3.connect(folder / 'trading.db')) as db, db:
            db.execute('create table strategies (id integer, enabled integer, ai_api_key_enc text)')
            db.execute('insert into strategies values (1,1,?)', (Fernet(key).encrypt(b'test-only').decode(),))
        return key

    def run_script(self, name, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / name), *map(str, args)],
            cwd=cwd, capture_output=True, text=True, encoding='utf-8',
            env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'), timeout=30)

    def test_restore_pauses_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, target = base / 'backup 中文 #1', base / 'restored 中文 #2'
            self.make_backup(source)
            result = self.run_script('restore.py', source, target)
            self.assertEqual(result.returncode, 0, result.stderr)
            with closing(sqlite3.connect(target / 'trading.db')) as db:
                self.assertEqual(db.execute('select enabled from strategies').fetchone()[0], 0)
            with closing(sqlite3.connect(source / 'trading.db')) as db:
                self.assertEqual(db.execute('select enabled from strategies').fetchone()[0], 1)
            self.assertEqual((source / '.env').read_bytes(), (target / '.env').read_bytes())
            self.assertNotEqual(self.run_script('restore.py', source, target).returncode, 0)

    def test_wrong_key_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, target = base / 'backup', base / 'restored'
            self.make_backup(source)
            (source / '.env').write_text('ENCRYPTION_KEY=' + Fernet.generate_key().decode() + '\n', encoding='utf-8')
            result = self.run_script('restore.py', source, target)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.exists())

    def test_backup_and_doctor_accept_unicode_and_reserved_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / '账户备份 #1'
            key = self.make_backup(source)
            result = self.run_script('backup.py', '--database', source / 'trading.db', '--env', source / '.env', cwd=base)
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list((base / 'backups').iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual((source / '.env').read_bytes(), (backups[0] / '.env').read_bytes())
            with closing(sqlite3.connect(backups[0] / 'trading.db')) as db:
                self.assertEqual(db.execute('select enabled from strategies').fetchone()[0], 1)
            result = self.run_script('doctor.py', '--database', source / 'trading.db', '--env', source / '.env')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('离线检查通过', result.stdout)
            self.assertNotIn(key.decode(), result.stdout + result.stderr)

    def test_scripts_explicitly_close_sqlite_connections(self):
        # 保留连接对象引用，确保结果不依赖垃圾回收或操作系统是否允许删除打开的文件。
        connect = sqlite3.connect
        connections = []

        def tracked_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, target = base / 'source #中文', base / 'restored'
            self.make_backup(source)
            commands = [
                ('backup.py', '--database', str(source / 'trading.db'), '--env', str(source / '.env')),
                ('doctor.py', '--database', str(source / 'trading.db'), '--env', str(source / '.env')),
                ('restore.py', str(source), str(target)),
            ]
            previous = Path.cwd()
            previous_umask = os.umask(0o077)
            try:
                os.chdir(base)
                for name, *args in commands:
                    with patch.object(sqlite3, 'connect', side_effect=tracked_connect), \
                            patch.object(sys, 'argv', [name, *args]), redirect_stdout(StringIO()):
                        try:
                            runpy.run_path(str(ROOT / 'scripts' / name), run_name='__main__')
                        except SystemExit as error:
                            self.assertEqual(error.code, 0)
                    for connection in connections:
                        with self.assertRaises(sqlite3.ProgrammingError):
                            connection.execute('select 1')
                self.assertGreaterEqual(len(connections), 6)
            finally:
                for connection in connections:
                    connection.close()
                os.chdir(previous)
                os.umask(previous_umask)

    def test_release_check_rejects_tracked_database(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '-q', directory], check=True)
            Path(directory, 'trading.db').write_text('test-only', encoding='utf-8')
            subprocess.run(['git', '-C', directory, 'add', 'trading.db'], check=True)
            result = self.run_script('release_check.py', cwd=directory)
            self.assertNotEqual(result.returncode, 0)
