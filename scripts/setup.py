"""首次初始化；已有密钥和数据库不覆盖。"""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.security import hash_password
from cryptography.fernet import Fernet

parser = argparse.ArgumentParser()
parser.add_argument('--reset-admin', action='store_true', help='重新设置管理员，不更换加密密钥')
args = parser.parse_args()

path = Path(__file__).resolve().parents[1] / '.env'
content = path.read_text(encoding="utf-8") if path.exists() else ''
from dotenv import dotenv_values
existing = {key for key,value in dotenv_values(path).items() if value} if path.exists() else set()
if 'ENCRYPTION_KEY' not in existing and (path.parent/'trading.db').exists():
    raise SystemExit('已有数据库但缺少加密密钥，请先恢复配套 .env，禁止生成替代密钥')
new = {}
if args.reset_admin or 'APP_PASSWORD_HASH' not in existing:
    username = input('管理员用户名：').strip()
    if not username or any(c in username for c in '\r\n#= '):
        raise SystemExit('用户名不能为空或包含空格、#、=')
    password = getpass.getpass('管理员密码（至少12位）：')
    if len(password) < 12 or password != getpass.getpass('再次输入密码：'):
        raise SystemExit('密码长度不足或两次输入不一致')
    new.update(APP_USERNAME=username, APP_PASSWORD_HASH=hash_password(password))
for key, value in [('ENCRYPTION_KEY', Fernet.generate_key().decode()), ('APP_SESSION_SECRET', secrets.token_urlsafe(48))]:
    if key not in existing:
        new[key] = value
kept = [line for line in content.splitlines() if line.split('=',1)[0].strip() not in new]
import tempfile
fd, temporary = tempfile.mkstemp(prefix='.env-',dir=path.parent)
try:
    with os.fdopen(fd,'w',encoding='utf-8') as output:
        output.write('\n'.join(kept) + '\n' + '\n'.join(f'{k}={v}' for k,v in new.items()) + '\n')
        output.flush();os.fsync(output.fileno())
    os.chmod(temporary,0o600)
    os.replace(temporary,path)
finally:
    if os.path.exists(temporary):os.unlink(temporary)
print('初始化完成。请备份 .env；不会生成或启动任何交易策略。')
