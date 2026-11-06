"""只处理 OKX USDT 线性永续合约；规格不明时拒绝计算。"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('数字缺失或格式无效') from None
    if not result.is_finite():
        raise ValueError('数字必须有限')
    return result


def inst_id(symbol):
    value = str(symbol or '').strip().upper()
    match = re.fullmatch(r'([A-Z0-9]+)/(USDT):USDT', value)
    if match:
        value = f'{match[1]}-USDT-SWAP'
    if not re.fullmatch(r'[A-Z0-9]+-USDT-SWAP', value):
        raise ValueError('仅支持明确的 USDT 永续合约标识')
    return value


@dataclass(frozen=True)
class Contract:
    instrument: str
    contract_size: Decimal
    lot_size: Decimal
    minimum: Decimal

    @classmethod
    def from_okx(cls, data):
        instrument = inst_id(data.get('instId'))
        base = instrument.split('-')[0]
        if data.get('ctType') != 'linear' or data.get('settleCcy') != 'USDT' or data.get('ctValCcy') != base:
            raise ValueError('合约类型或面值币种无法确认')
        size = number(data.get('ctVal')) * number(data.get('ctMult') or '1')
        lot, minimum = number(data.get('lotSz')), number(data.get('minSz'))
        if min(size, lot, minimum) <= 0:
            raise ValueError('合约面值、步长、最小张数必须为正')
        return cls(instrument, size, lot, minimum)

    def amounts(self, contracts, price):
        count, px = number(contracts), number(price)
        if count < 0 or px <= 0:
            raise ValueError('张数或价格无效')
        return {'contracts': str(count), 'base_quantity': str(count * self.contract_size),
                'notional_usdt': str(count * self.contract_size * px)}

    def remaining_contracts(self, budget, price, held, pending):
        """held/pending 必须来自已核实的同方向仓位和未成交开仓单。"""
        cap, px, pos, orders = map(number, (budget, price, held, pending))
        if cap <= 0 or px <= 0 or min(pos, orders) < 0:
            raise ValueError('预算、价格或敞口无效')
        remaining = max(Decimal(0), cap / (px * self.contract_size) - pos - orders)
        quantity = (remaining // self.lot_size) * self.lot_size
        return quantity if quantity >= self.minimum else Decimal(0)
