"""部署前离线检查，不连接交易所，不展示密钥。"""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from cryptography.fernet import Fernet

parser=argparse.ArgumentParser()
parser.add_argument('--env',default='.env')
parser.add_argument('--database',default='trading.db')
args=parser.parse_args()
config=dotenv_values(args.env)
failures=[]
for key in ['APP_USERNAME','APP_PASSWORD_HASH','APP_SESSION_SECRET','ENCRYPTION_KEY']:
    if not config.get(key):failures.append(f'缺少 {key}')
if len(config.get('APP_SESSION_SECRET',''))<32:failures.append('会话密钥长度不足32字符')
try:fernet=Fernet(config.get('ENCRYPTION_KEY','').encode())
except Exception:fernet=None;failures.append('加密密钥格式无效')
if os.name!='nt' and Path(args.env).exists() and Path(args.env).stat().st_mode & 0o007:failures.append('.env 对其他用户开放了访问权限')
if Path(args.database).is_file():
    with sqlite3.connect(f'file:{Path(args.database).resolve()}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':failures.append('数据库完整性检查失败')
        tables={row[0] for row in db.execute("select name from sqlite_master where type='table'")}
        if 'strategies' in tables:
            enabled=db.execute('select count(*) from strategies where enabled=1').fetchone()[0]
            print(f'启用策略：{enabled}；启动服务会重新加载，迁移前请暂停')
        for table in ['system_config','strategies']:
            if table not in tables:continue
            columns=[row[1] for row in db.execute(f'PRAGMA table_info({table})') if row[1].endswith('_enc')]
            for column in columns:
                for (value,) in db.execute(f'SELECT {column} FROM {table}'):
                    if value:
                        try:
                            if fernet is None:raise ValueError()
                            fernet.decrypt(value.encode())
                        except Exception:failures.append(f'{table}.{column} 无法使用当前密钥解密');break
else:print('尚无数据库：首次启动时创建')
for failure in failures:print('失败：'+failure)
print('离线检查'+('失败' if failures else '通过；未验证外部服务连接'))
raise SystemExit(bool(failures))
