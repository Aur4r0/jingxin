"""只读展示辅助函数；不执行交易或修改模型数据。"""
from datetime import timezone
from decimal import Decimal, InvalidOperation


def ui_number(value, digits=2, signed=False):
    if value is None:
        return '—'
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            return '—'
        text = format(result, f'+,.{digits}f' if signed else f',.{digits}f')
        return text.lstrip('+-') if Decimal(text.replace(',', '')) == 0 else text
    except (ValueError, TypeError, InvalidOperation):
        return '—'


def ui_tone(value):
    try:
        value = Decimal(str(value))
        return 'positive' if value.is_finite() and value > 0 else 'negative' if value.is_finite() and value < 0 else 'neutral'
    except (ValueError, TypeError, InvalidOperation):
        return 'neutral'


def utc_iso(value):
    if not value:
        return ''
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


def position_pnl(positions):
    if not positions or any(p.unrealized_pnl is None for p in positions):
        return None
    try:
        values = [Decimal(str(p.unrealized_pnl)) for p in positions]
        return sum(values) if all(v.is_finite() for v in values) else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def execution_state(log):
    if log is None:
        return {'label': '暂无执行', 'kind': 'neutral', 'description': '尚无本地执行记录'}
    if log.order_placed:
        return {'label': '已提交 · 待核对' if log.error_message else '已提交 · 成交未确认',
                'kind': 'warning' if log.error_message else 'neutral',
                'description': log.error_message or '本记录只证明订单请求已提交，成交请查看历史交易'}
    if log.error_message:
        skipped = '已跳过' in log.error_message or '本轮' in log.error_message and '跳过' in log.error_message
        return {'label': '本轮跳过' if skipped else '执行异常', 'kind': 'warning' if skipped else 'negative', 'description': log.error_message}
    return {'label': '持有 · 未下单' if log.parsed_action == 'hold' else '未记录下单', 'kind': 'neutral',
            'description': log.parsed_reasoning or '无补充说明，不代表执行失败'}
