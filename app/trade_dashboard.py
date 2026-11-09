"""历史交易只读查询：北京时间筛选、完整区间汇总和明细分页。"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from app.contracts import inst_id, number
from app.fill_ledger import account_key, fill_view
from app.models import ExecutionFill, SystemConfig, Trade

BJ = ZoneInfo('Asia/Shanghai')
PERIODS = [('today', '今天'), ('yesterday', '昨天'), ('7d', '最近7天'),
           ('30d', '最近30天'), ('custom', '自定义'), ('all', '全部已同步')]


@dataclass(frozen=True)
class DateRange:
    period: str
    start: date | None
    end: date | None

    @property
    def bounds(self):
        if self.start is None:
            return None, None
        convert = lambda d: datetime.combine(d, time.min, BJ).astimezone(timezone.utc).replace(tzinfo=None)
        return convert(self.start), convert(self.end + timedelta(days=1))

    @property
    def label(self):
        if self.start is None:
            return '全部已同步记录 · 北京时间'
        if self.start == self.end:
            return self.start.isoformat() + ' · 北京时间'
        return self.start.isoformat() + ' 至 ' + self.end.isoformat() + ' · 北京时间'


def date_range(period='today', start='', end='', now=None):
    today = (now or datetime.now(timezone.utc)).astimezone(BJ).date()
    if period == 'today':
        return DateRange(period, today, today)
    if period == 'yesterday':
        day = today - timedelta(days=1)
        return DateRange(period, day, day)
    if period in ('7d', '30d'):
        return DateRange(period, today - timedelta(days=6 if period == '7d' else 29), today)
    if period == 'all':
        return DateRange(period, None, None)
    if period != 'custom':
        raise ValueError('日期选项无效，请重新选择')
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError('请选择完整的开始日期和结束日期') from None
    if first < date(1970, 1, 1):
        raise ValueError('开始日期不能早于1970年')
    if first > last:
        raise ValueError('开始日期不能晚于结束日期')
    if last >= date.max or (last - first).days >= 366:
        raise ValueError('自定义日期区间最长366天，请缩小范围')
    return DateRange(period, first, last)


def money(value, signed=True):
    if value is None:
        return '待核实'
    value = number(value)
    # 防止舍入后的 -0.0000 被误认作真实亏损。
    rendered = format(value, '+.4f' if signed else '.4f')
    if not number(rendered):
        return '0.0000'
    return rendered


def tone(value):
    if value is None or money(value) == '0.0000':
        return 'neutral'
    return 'positive' if number(value) > 0 else 'negative'


def accumulate(rows):
    gross = fees = cost = rebate = Decimal(0)
    missing_pnl = missing_fee = unknown = count = 0
    orders = set()
    for row in rows:
        count += 1
        orders.add(row.order_id)
        pnl_ok = row.realized_pnl is not None
        fee_ok = row.fee_signed is not None and row.fee_currency == 'USDT'
        missing_pnl += not pnl_ok
        missing_fee += not fee_ok
        unknown += not (pnl_ok and fee_ok)
        if pnl_ok:
            gross += number(row.realized_pnl)
        if fee_ok:
            fee = number(row.fee_signed)
            fees += fee
            cost += -fee if fee < 0 else 0
            rebate += fee if fee > 0 else 0
    return dict(count=count, orders=len(orders), unknown=unknown,
                pnl_unknown=missing_pnl, fee_unknown=missing_fee,
                gross=gross if count and not missing_pnl else None,
                fees_cost=-fees if count and not missing_fee else None,
                fees_signed=fees if count and not missing_fee else None,
                net=gross + fees if count and not unknown else None,
                cost=cost if count and not missing_fee else None,
                rebate=rebate if count and not missing_fee else None,
                known_gross=gross, known_cost=cost, known_rebate=rebate)


def dashboard(db, period='today', start_date='', end_date='', symbol='', page=1, page_size=10, now=None):
    selected = date_range(period, start_date, end_date, now)
    if page < 1 or page_size not in (10, 20, 50):
        raise ValueError('分页参数无效，每页可选10、20或50条')
    scope = account_key(db.query(SystemConfig).first())
    base = db.query(ExecutionFill).filter(ExecutionFill.environment == 'demo', ExecutionFill.account_key == scope)
    symbols = [s[0] for s in base.with_entities(ExecutionFill.symbol).distinct().order_by(ExecutionFill.symbol)]
    if symbol:
        symbol = inst_id(symbol)
    q = base
    lower, upper = selected.bounds
    if lower is not None:
        q = q.filter(ExecutionFill.filled_at >= lower, ExecutionFill.filled_at < upper)
    if symbol:
        q = q.filter(ExecutionFill.symbol == symbol)
    # 成交量通常较小；流式汇总避免所有明细占满内存。每天只保留累计值。
    totals = accumulate(q.yield_per(500))
    buckets = {}
    # 单次流式读取按北京时间自然日分组，每日累计无需保留所有成交行。
    from itertools import groupby
    ordered = q.order_by(ExecutionFill.filled_at, ExecutionFill.id).yield_per(500)
    for day, rows in groupby(ordered, lambda f: f.filled_at.replace(tzinfo=timezone.utc).astimezone(BJ).date()):
        buckets[day] = accumulate(rows)
    chart = []
    if selected.start is not None:
        dates = [selected.start + timedelta(days=i) for i in range((selected.end - selected.start).days + 1)]
    else:
        # 全部记录模式只画存在成交的日期，不把缺失日期补成零。
        dates = sorted(buckets)
    for day in dates:
        entry = buckets.get(day, accumulate([]))
        chart.append(dict(date=day.isoformat(), count=entry['count'], unknown=entry['unknown'],
                          gross=str(entry['gross']) if entry['gross'] is not None else None,
                          fees_cost=str(entry['fees_cost']) if entry['fees_cost'] is not None else None,
                          net=str(entry['net']) if entry['net'] is not None else None))
    total_pages = max(1, (totals['count'] + page_size - 1) // page_size)
    page = min(page, total_pages)
    rows = q.order_by(ExecutionFill.filled_at.desc(), ExecutionFill.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    params = dict(period=period, start_date=start_date, end_date=end_date, symbol=symbol, page_size=page_size)
    link = lambda p: '/trades?' + urlencode(dict(params, page=p))
    min_row = base.order_by(ExecutionFill.filled_at).first()
    max_row = base.order_by(ExecutionFill.filled_at.desc()).first()
    known_range = None
    if min_row:
        fmt = lambda row: row.filled_at.replace(tzinfo=timezone.utc).astimezone(BJ).strftime('%Y-%m-%d')
        known_range = fmt(min_row) + ' 至 ' + fmt(max_row)
    return dict(summary=totals, fills=[fill_view(f) for f in rows], total=totals['count'],
                page=page, page_size=page_size, total_pages=total_pages, chart=chart,
                prev_url=link(max(1, page-1)), next_url=link(min(total_pages, page+1)),
                period=period, start_date=start_date, end_date=end_date, symbol=symbol,
                symbols=symbols, range_label=selected.label, known_range=known_range,
                first_record=None if not min_row else min_row.filled_at,
                coverage_warning='仅统计已入库成交，当前未保存可证明区间完整覆盖的同步记录；无记录的日期不代表没有交易。')


def public_stats(view):
    # Decimal 转字符串，避免 API 将精确金额转成二进制浮点数。
    summary = {k: str(v) if isinstance(v, Decimal) else v for k, v in view['summary'].items()}
    return dict(summary=summary, daily=view['chart'], range_label=view['range_label'],
                period=view['period'], symbol=view['symbol'], coverage_warning=view['coverage_warning'])
