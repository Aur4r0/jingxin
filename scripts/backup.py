"""SQLite 一致性备份，目录同时保存解密所需 .env；切勿公开。"""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import argparse
import os
import shutil
import sqlite3

parser=argparse.ArgumentParser()
parser.add_argument('--database',default='trading.db')
parser.add_argument('--env',default='.env')
args=parser.parse_args()
if not Path(args.database).is_file() or not Path(args.env).is_file():
    raise SystemExit('数据库或 .env 不存在，取消备份')
os.umask(0o077)
folder=Path('backups')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
folder.mkdir(parents=True)
with (
    closing(sqlite3.connect(Path(args.database).resolve().as_uri()+'?mode=ro',uri=True)) as source,
    closing(sqlite3.connect(folder/'trading.db')) as dest,
    dest,
):
    source.backup(dest)
shutil.copyfile(args.env,folder/'.env')
print('备份完成：'+str(folder.resolve())+'；包含敏感配置，请加密保管。')
