"""检查 Git 发布候选路径，不读取或输出秘密内容，不执行推送。"""
from pathlib import PurePosixPath
import subprocess
import sys

paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0')
bad=[]
for path in filter(None,paths):
    name=PurePosixPath(path).name
    if (name=='.env' or name.startswith('.env-') or name.startswith('.env.') and name!='.env.example'
        or '.db' in name or any(part in ('backups','data','.venv') for part in PurePosixPath(path).parts)):
        bad.append(path)
for path in sorted(set(bad)):print('禁止发布：'+path)
print('发布路径检查'+('失败' if bad else '通过；仍须人工审查 git diff --cached 和历史提交'))
sys.exit(bool(bad))
