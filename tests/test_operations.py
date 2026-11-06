import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from cryptography.fernet import Fernet

ROOT=Path(__file__).resolve().parents[1]

class OperationsTests(unittest.TestCase):
    def make_backup(self,folder):
        folder.mkdir();key=Fernet.generate_key()
        (folder/'.env').write_text('ENCRYPTION_KEY='+key.decode()+'\n')
        with sqlite3.connect(folder/'trading.db') as db:
            db.execute('create table strategies (id integer, enabled integer, ai_api_key_enc text)')
            db.execute('insert into strategies values (1,1,?)',(Fernet(key).encrypt(b'test-only').decode(),))
        return key
    def test_restore_pauses_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'backup';target=base/'restored';self.make_backup(source)
            command=[sys.executable,str(ROOT/'scripts/restore.py'),str(source),str(target)]
            result=subprocess.run(command,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with sqlite3.connect(target/'trading.db') as db:self.assertEqual(db.execute('select enabled from strategies').fetchone()[0],0)
            with sqlite3.connect(source/'trading.db') as db:self.assertEqual(db.execute('select enabled from strategies').fetchone()[0],1)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
    def test_wrong_key_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'backup';target=base/'restored';self.make_backup(source)
            (source/'.env').write_text('ENCRYPTION_KEY='+Fernet.generate_key().decode()+'\n')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/restore.py'),str(source),str(target)],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(target.exists())
    def test_release_check_rejects_tracked_database(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git','init','-q',directory],check=True)
            Path(directory,'trading.db').write_text('test-only')
            subprocess.run(['git','-C',directory,'add','trading.db'],check=True)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/release_check.py')],cwd=directory,capture_output=True)
            self.assertNotEqual(result.returncode,0)
