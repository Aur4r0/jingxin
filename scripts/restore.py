"""只恢复到新的空目录，默认暂停全部策略，不覆盖运行实例。"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
from dotenv import dotenv_values
from cryptography.fernet import Fernet

parser=argparse.ArgumentParser()
parser.add_argument('backup',type=Path)
parser.add_argument('destination',type=Path)
args=parser.parse_args()
source=args.backup.resolve();target=args.destination.resolve()
if target.exists():raise SystemExit('目标目录已存在，取消恢复；请使用全新的目录')
if not (source/'.env').is_file() or not (source/'trading.db').is_file():raise SystemExit('备份必须包含 .env 和 trading.db')
try:
    config=dotenv_values(source/'.env');fernet=Fernet(config['ENCRYPTION_KEY'].encode())
    with closing(sqlite3.connect((source/'trading.db').as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError()
        tables={row[0] for row in db.execute("select name from sqlite_master where type='table'")}
        if 'strategies' not in tables:raise ValueError()
        for table in ['system_config','strategies']:
            for column in [row[1] for row in db.execute(f'PRAGMA table_info({table})') if row[1].endswith('_enc')]:
                for (value,) in db.execute(f'SELECT {column} FROM {table}'):
                    if value:fernet.decrypt(value.encode())
except Exception:raise SystemExit('备份或配套密钥验证失败，未创建目标目录')
os.umask(0o077)
target.mkdir(parents=True)
with (
    closing(sqlite3.connect((source/'trading.db').as_uri()+'?mode=ro',uri=True)) as original,
    closing(sqlite3.connect(target/'trading.db')) as restored,
    restored,
):
    original.backup(restored)
    restored.execute('UPDATE strategies SET enabled=0')
    restored.commit()
(target/'.env').write_bytes((source/'.env').read_bytes())
os.chmod(target/'.env',0o600)
print('恢复完成，全部策略已暂停；未启动服务。请人工核对交易所持仓、环境、代理和 IP 白名单。')
