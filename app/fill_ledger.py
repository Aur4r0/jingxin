"""模拟盘成交同步：只读取交易所成交，写入独立本地账本。"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from threading import Lock
from sqlalchemy.dialects.sqlite import insert
from app.contracts import inst_id, number
from app.models import ExecutionFill, SystemConfig
from app.config import decrypt_value
from app.reconciliation import paged

_sync_lock = Lock()


def demo_credentials(cfg):
    if cfg is None or not cfg.okx_simulated:
        raise ValueError('仅支持当前模拟盘账户，实盘成交同步尚未启用')
    values = [decrypt_value(getattr(cfg, f'okx_sim_{name}_enc') or '')
              for name in ('api_key', 'secret_key', 'passphrase')]
    if any(not v or v != v.strip() for v in values):
        raise ValueError('请先保存完整的独立模拟盘凭据，不回退实盘账户')
    return values


def account_key(cfg):
    return sha256(('okx:demo:' + demo_credentials(cfg)[0]).encode()).hexdigest()


def parse_fill(row, scope):
    symbol = inst_id(row.get('instId'))
    oid, fid = str(row.get('ordId') or ''), str(row.get('tradeId') or '')
    if not oid or not fid or row.get('side') not in ('buy', 'sell'):
        raise ValueError('成交缺少标识或买卖方向')
    price, quantity = number(row.get('fillPx')), number(row.get('fillSz'))
    if price <= 0 or quantity <= 0:
        raise ValueError('成交价格或张数无效')
    timestamp = number(row.get('ts'))
    if timestamp <= 0:
        raise ValueError('成交时间无效')
    filled_at = datetime.fromtimestamp(float(timestamp / 1000), timezone.utc).replace(tzinfo=None)
    optional = lambda field: None if row.get(field) in (None, '') else str(number(row[field]))
    return dict(environment='demo', account_key=scope, symbol=symbol, order_id=oid, fill_id=fid,
                bill_id=str(row.get('billId') or ''), side=row['side'], position_side=row.get('posSide') or '',
                subtype=str(row.get('subType') or ''), price=str(price), contracts=str(quantity),
                realized_pnl=optional('fillPnl'), fee_signed=optional('fee'), fee_currency=row.get('feeCcy') or '',
                filled_at=filled_at, source='okx_fills_history')


def store_fills(db, rows, scope):
    # 全部验证完再写入；任何错误由调用方回滚，不产生半批入库。
    parsed = [parse_fill(row, scope) for row in rows]
    added = 0
    for fill in parsed:
        result = db.execute(insert(ExecutionFill).values(**fill).on_conflict_do_nothing(
            index_elements=['environment', 'account_key', 'symbol', 'order_id', 'fill_id']))
        added += result.rowcount
        if not result.rowcount:
            existing = db.query(ExecutionFill).filter_by(environment='demo', account_key=scope,
                symbol=fill['symbol'], order_id=fill['order_id'], fill_id=fill['fill_id']).one()
            if number(existing.price) != number(fill['price']) or number(existing.contracts) != number(fill['contracts']):
                raise ValueError('相同成交标识的数据冲突，本轮取消入库')
            for field in ('realized_pnl', 'fee_signed', 'fee_currency'):
                if getattr(existing, field) in (None, '') and fill[field] not in (None, ''):
                    setattr(existing, field, fill[field])
    return added


def sync_demo_fills(db):
    if not _sync_lock.acquire(blocking=False):
        raise ValueError('成交同步正在执行，请稍后刷新')
    client = None
    try:
        cfg = db.query(SystemConfig).first()
        creds, scope = demo_credentials(cfg), account_key(cfg)
        proxy = cfg.okx_proxy
        db.rollback()  # 释放读取事务，网络请求后重新核对账户配置。
        import ccxt
        client = ccxt.okx({'apiKey': creds[0], 'secret': creds[1], 'password': creds[2],
                           'headers': {'x-simulated-trading': '1'}, 'enableRateLimit': True, 'timeout': 15000})
        client.session.verify = True
        if proxy:
            client.session.proxies = {'http': proxy, 'https': proxy}
        # 首次导入最近七天，以后保留七天重叠窗口，补偿延迟与失败；不删除已有历史。
        begin = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
        rows, complete = paged(client, 'trade/fills-history', {'instType': 'SWAP', 'begin': str(begin)}, 'billId', 10)
        if not complete:
            raise ValueError('成交分页不完整，本轮未写入；请先用只读工具核对')
        # 仅接受当前支持的 USDT SWAP；其他产品不计入 USDT 交易账本。
        supported = []
        for row in rows:
            if str(row.get('instId', '')).endswith('-USDT-SWAP'):
                supported.append(row)
        db.expire_all()
        if account_key(db.query(SystemConfig).first()) != scope:
            raise ValueError('同步期间账户配置发生变化，本轮已取消')
        added = store_fills(db, supported, scope)
        db.commit()
        return {'added': added, 'received': len(supported), 'window_days': 7,
                'message': f'同步成功，新增 {added} 笔成交；仅最近7天的 USDT 永续合约，不含资金费'}
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            if client is not None:
                client.session.close()
        finally:
            _sync_lock.release()


def fill_summary(rows):
    gross = Decimal(0)
    fees = Decimal(0)
    pnl_unknown = fee_unknown = 0
    for fill in rows:
        if fill.realized_pnl is None:
            pnl_unknown += 1
        else:
            gross += number(fill.realized_pnl)
        if fill.fee_signed is None or fill.fee_currency != 'USDT':
            fee_unknown += 1
        else:
            fees += number(fill.fee_signed)
    return dict(gross=gross if not pnl_unknown else None, fees_signed=fees if not fee_unknown else None,
                net=gross + fees if not pnl_unknown and not fee_unknown else None,
                known_gross=gross, known_fees_signed=fees, pnl_unknown=pnl_unknown, fee_unknown=fee_unknown)


def fill_view(fill):
    subtype = fill.subtype
    action = {'3': '开多', '4': '开空', '5': '平多', '6': '平空',
              '100': '强平多', '101': '强平空', '104': '强平多', '105': '强平空',
              '125': 'ADL平多', '126': 'ADL平空'}.get(subtype, '买入' if fill.side == 'buy' else '卖出')
    pnl = number(fill.realized_pnl) if fill.realized_pnl is not None else None
    fee = number(fill.fee_signed) if fill.fee_signed is not None else None
    return {'record': fill, 'action': action, 'pnl': pnl, 'fee': fee,
            'net': pnl + fee if pnl is not None and fee is not None and fill.fee_currency == 'USDT' else None}
