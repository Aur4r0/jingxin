"""模拟盘只读快照，不写账本、不启动调度器、不修改订单。"""
from datetime import datetime, timezone
from collections import defaultdict
from app.contracts import Contract, inst_id, number

READ_PATHS = frozenset({'public/instruments', 'account/positions', 'trade/order',
                        'trade/orders-pending', 'trade/fills-history', 'trade/orders-algo-pending'})
STATUS = {'live': 'submitted', 'partially_filled': 'partially_filled', 'filled': 'filled',
          'canceled': 'canceled', 'mmp_canceled': 'canceled', 'order_failed': 'rejected'}


def read(client, path, params):
    if path not in READ_PATHS:
        raise ValueError('接口不在只读白名单')
    response = client.request(path, 'public' if path.startswith('public/') else 'private', 'GET', params)
    if not isinstance(response, dict) or str(response.get('code')) != '0' or not isinstance(response.get('data'), list):
        raise ValueError('交易所响应无效')
    return response['data']


def paged(client, path, params, cursor_key, max_pages):
    rows, seen, cursor = [], set(), None
    for _ in range(max_pages):
        query = dict(params, limit='100')
        if cursor:
            query['after'] = cursor
        page = read(client, path, query)
        rows.extend(page)
        if len(page) < 100:
            return rows, True
        cursor = page[-1].get(cursor_key)
        if not cursor or cursor in seen:
            return rows, False
        seen.add(cursor)
    return rows, False


def pick(row, fields):
    return {key: row.get(key) for key in fields.split()}


def summarize_fills(rows):
    unique, seen = [], set()
    for row in rows:
        # billId 是分页账单标识；成交号仅在合约内使用，不单独当全局键。
        key = (row.get('instId'), row.get('tradeId'), row.get('ordId'))
        if not all(key):
            raise ValueError('成交缺少唯一标识')
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    groups = defaultdict(list)
    for row in unique:
        groups[(row['instId'], row['ordId'])].append(row)
    totals = []
    for (instrument, order), fills in groups.items():
        quantity = sum(number(f['fillSz']) for f in fills)
        if quantity <= 0:
            raise ValueError('成交张数无效')
        fees = defaultdict(lambda: number(0))
        pnl = None
        if all(f.get('fillPnl') not in (None, '') for f in fills):
            pnl = str(sum(number(f['fillPnl']) for f in fills))
        fee_complete = all(f.get('feeCcy') and f.get('fee') not in (None, '') for f in fills)
        for f in fills:
            if f.get('feeCcy') and f.get('fee') not in (None, ''):
                fees[f['feeCcy']] += number(f['fee'])
        totals.append({'instId': instrument, 'ordId': order, 'contracts_in_window': str(quantity),
                       'fill_average_in_window': str(sum(number(f['fillPx']) * number(f['fillSz']) for f in fills) / quantity),
                       'realized_pnl_in_window': pnl, 'fees_signed_by_currency': {c: str(v) for c, v in fees.items()},
                       'fee_complete': fee_complete,
                       'net_pnl_usdt_in_window': str(number(pnl) + sum(fees.values()))
                       if pnl is not None and fee_complete and set(fees) == {'USDT'} else None})
    return unique, totals


def collect(client, instrument, local_orders, begin_ms, max_pages=10):
    instrument = inst_id(instrument)
    report = {'environment': 'demo', 'read_only': True, 'instId': instrument,
              'started_at': datetime.now(timezone.utc).isoformat(), 'begin_ms': begin_ms,
              'warnings': [], 'coverage': {}, 'local_orders': local_orders}
    warnings = report['warnings']
    def section(name, function):
        try:
            result = function()
            report['coverage'][name] = True
            return result
        except Exception:
            # 异常文本可能包含凭据、请求头或代理 URL，不写入报告。
            report['coverage'][name] = False
            warnings.append(name + '读取失败或数据无法核实；不得据此恢复策略')
            return None
    specs = section('specification', lambda: Contract.from_okx(read(client, 'public/instruments', {'instType': 'SWAP', 'instId': instrument})[0]))
    if specs:
        report['specification'] = {k: str(v) for k, v in vars(specs).items()}
    positions = section('positions', lambda: read(client, 'account/positions', {'instId': instrument}))
    report['positions'] = []
    if positions is not None:
        for p in positions:
            item = pick(p, 'instId posSide pos avgPx markPx upl lever margin mgnMode')
            if specs:
                item['units'] = section('position_units', lambda p=p: specs.amounts(abs(number(p['pos'])), p['markPx']))
            report['positions'].append(item)
    for name, path, params, key in [
        ('pending_orders', 'trade/orders-pending', {'instType': 'SWAP', 'instId': instrument}, 'ordId'),
        ('fills', 'trade/fills-history', {'instType': 'SWAP', 'instId': instrument, 'begin': str(begin_ms)}, 'billId'),
        ('conditional', 'trade/orders-algo-pending', {'ordType': 'conditional', 'instId': instrument}, 'algoId'),
        ('oco', 'trade/orders-algo-pending', {'ordType': 'oco', 'instId': instrument}, 'algoId')]:
        result = section(name, lambda path=path, params=params, key=key: paged(client, path, params, key, max_pages))
        rows, complete = result if result is not None else ([], False)
        report['coverage'][name] = complete
        if not complete:
            warnings.append(name + '结果不完整，不能判断不存在订单或成交')
        fields = 'instId ordId tradeId billId fillSz fillPx fillPnl fee feeCcy side posSide ts subType' if name == 'fills' else 'instId ordId algoId posSide side sz accFillSz state reduceOnly closeFraction tpTriggerPx slTriggerPx'
        report[name] = [pick(r, fields) for r in rows]
    summary = section('fill_summary', lambda: summarize_fills(report['fills']))
    if summary:
        report['fills'], report['fill_totals'] = summary
    report['orders'] = []
    for row in local_orders:
        oid = row.get('order_id')
        if not oid:
            continue
        data = section('order:' + oid, lambda oid=oid: read(client, 'trade/order', {'instId': instrument, 'ordId': oid}))
        item = pick(data[0], 'ordId instId state sz accFillSz avgPx fee feeCcy pnl algoId') if data else {'ordId': oid}
        item['status'] = STATUS.get(item.get('state'), 'unknown')
        item['local_record'] = row
        report['orders'].append(item)
    if positions is not None:
        for algo in report['conditional'] + report['oco']:
            try:
                if algo.get('closeFraction'):
                    warnings.append('保护单 ' + str(algo['algoId']) + ' 使用比例平仓，需人工核对')
                    continue
                side = algo.get('posSide')
                if side not in ('long', 'short', 'net'):
                    raise ValueError()
                # net 仓位用买卖方向与 pos 正负对应，不能把多空敞口合并。
                exposure = sum(abs(number(p['pos'])) for p in positions if p.get('posSide') == side and
                               (side != 'net' or (number(p['pos']) > 0 and algo.get('side') == 'sell') or
                                (number(p['pos']) < 0 and algo.get('side') == 'buy')))
                if number(algo.get('sz')) > exposure:
                    warnings.append('保护单 ' + str(algo['algoId']) + ' 张数超过对应当前持仓；请人工核对，工具未撤单')
            except Exception:
                warnings.append('保护单数量或方向无法核实，请人工核对')
    known = {str(r.get('order_id')) for r in local_orders}
    report['fills_without_local_order'] = [f for f in report['fills'] if f.get('ordId') not in known]
    report['limitations'] = ['仅为指定合约和时间范围内的非原子快照；历史成交可能超出接口保留期',
                            '本地旧记录的价格、数量和 filled 状态未经验证，不作为成交依据',
                            '未归属成交不自动分配给策略；保护单与策略的关联仍需核实',
                            '费用保留交易所符号：负值为扣费，正值为返佣；资金费未读取，不包含在净交易盈亏中',
                            '未实现账本回写、订单恢复或保护单自动管理；报告不是恢复策略的许可']
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    return report
