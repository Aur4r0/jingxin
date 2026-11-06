"""Windows 配置入口；只使用标准库引导，不执行交易或修改系统策略。"""
from pathlib import Path
import os
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    if sys.platform != 'win32':
        raise RuntimeError('此入口仅用于 Windows，请参考 README 的其他系统步骤')
    if sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        raise RuntimeError('请安装 Python 3.12 64 位；不会自动替换现有 Python')
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if (ROOT / '.venv').exists():
        if not python.is_file():
            raise RuntimeError('已有 .venv 不是可用的 Windows 环境，请手动重命名该目录后重试；不要删除数据库或 .env')
        run([str(python), '-c', "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, '虚拟环境需要 Python 3.12 64 位'"])
    else:
        print('[1/4] 创建项目独立环境', flush=True)
        run([sys.executable, '-m', 'venv', str(ROOT / '.venv')])
    print('[2/4] 安装项目依赖，首次运行需要联网', flush=True)
    run([str(python), '-m', 'pip', 'install', '--timeout', '120', '--retries', '5', '-r', 'requirements.txt'])
    print('[3/4] 初始化管理员，密码输入不回显；已有配置和密钥保留', flush=True)
    run([str(python), 'scripts/setup.py'])
    print('[4/4] 离线检查配置，不调用交易所', flush=True)
    run([str(python), 'scripts/doctor.py'])
    print('配置完成。API、AI 和 Telegram 可在启动后的设置页填写。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('配置失败：' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n用户取消，已有配置保留。', file=sys.stderr)
        sys.exit(130)
