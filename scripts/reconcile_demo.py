"""生成模拟盘只读对账报告。不会导入引擎或创建数据库。"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.contracts import inst_id
from app.reconciliation import collect


def load_local(database, env, instrument):
    from dotenv import dotenv_values
    from cryptography.fernet import Fernet
    if not database.is_file() or not env.is_file():
        raise ValueError('数据库或配套 .env 不存在')
    key = dotenv_values(env).get('ENCRYPTION_KEY')
    cipher = Fernet(key.encode())
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        cfg = db.execute('SELECT * FROM system_config LIMIT 1').fetchone()
        if not cfg or not cfg['okx_simulated']:
            raise ValueError('仅允许当前已选择模拟盘的数据库')
        creds = []
        for field in ('okx_sim_api_key_enc', 'okx_sim_secret_key_enc', 'okx_sim_passphrase_enc'):
            value = cfg[field]
            if not value:
                raise ValueError('缺少独立模拟盘凭据；禁止回退实盘字段')
            plain = cipher.decrypt(value.encode()).decode()
            if not plain or plain != plain.strip():
                raise ValueError('模拟盘凭据为空或包含前后空格')
            creds.append(plain)
        rows = db.execute('SELECT id,strategy_id,symbol,order_id,status,price,quantity,pnl,fee,tp_order_id,sl_order_id FROM trades').fetchall()
        local = []
        for row in rows:
            try:
                if inst_id(row['symbol']) == instrument:
                    local.append(dict(row))
            except ValueError:
                continue
        enabled = db.execute('SELECT count(*) FROM strategies WHERE enabled=1').fetchone()[0]
        return creds, cfg['okx_proxy'] or '', local, enabled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('trading.db'))
    parser.add_argument('--env', type=Path, default=Path('.env'))
    parser.add_argument('--inst-id', default='BTC-USDT-SWAP')
    parser.add_argument('--days', type=int, choices=range(1, 91), default=7)
    parser.add_argument('--max-pages', type=int, choices=range(1, 101), default=10)
    parser.add_argument('--order-id', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        instrument = inst_id(args.inst_id)
        creds, proxy, local, enabled = load_local(args.database, args.env, instrument)
        for oid in args.order_id:
            if not oid.isdigit():
                raise ValueError('订单 ID 必须是数字')
            if not any(r['order_id'] == oid for r in local):
                local.append({'order_id': oid, 'source': 'operator_supplied'})
        # 专用客户端，不复用在线服务的缓存、调度器或交易辅助函数。
        import ccxt
        client = ccxt.okx({'apiKey': creds[0], 'secret': creds[1], 'password': creds[2],
                           'headers': {'x-simulated-trading': '1'}, 'enableRateLimit': True, 'timeout': 15000})
        client.session.verify = True
        if proxy:
            client.session.proxies = {'http': proxy, 'https': proxy}
        begin = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
        try:
            report = collect(client, instrument, local, begin, args.max_pages)
        finally:
            client.session.close()
        report['enabled_strategy_count'] = enabled
        if enabled:
            report['warnings'].insert(0, '数据库仍有启用策略；请先人工暂停，报告不会修改启用状态')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # 禁止覆盖，避免误写到 .env、数据库或已有报告。
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print('只读报告已保存；包含账户交易记录，请勿公开：' + str(args.output))
        print('告警数量：' + str(len(report['warnings'])) + '；未修改数据库或交易所')
        return 0 if all(report['coverage'].values()) else 2
    except Exception:
        print('对账失败：请检查模拟盘环境、配套密钥、凭据、路径及网络；未打印敏感错误详情。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
