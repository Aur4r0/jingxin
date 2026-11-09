"""Trading, positions, and logs API routes"""

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models import StrategyLog, Trade, Position, EquitySnapshot, get_db
from app.schemas import (
    StrategyLogOut, TradeOut, PositionOut, EquitySnapshotOut, ManualCloseRequest,
)
from app.exchange import close_position as exchange_close_position, fetch_positions
from app.engine import sync_positions

router = APIRouter(prefix="/api", tags=["trading"])


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _fee_cost(order: dict) -> float:
    fee = _as_dict(_as_dict(order).get("fee"))
    return _to_float(fee.get("cost"), 0.0)


# ──────────── Strategy Logs ────────────

@router.get("/logs", response_model=list[StrategyLogOut])
def list_logs(
    strategy_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(StrategyLog).order_by(StrategyLog.id.desc())
    if strategy_id:
        q = q.filter(StrategyLog.strategy_id == strategy_id)
    total = q.count()
    logs = q.offset((page - 1) * page_size).limit(page_size).all()
    return logs


@router.get("/logs/count")
def logs_count(strategy_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(StrategyLog)
    if strategy_id:
        q = q.filter(StrategyLog.strategy_id == strategy_id)
    return {"count": q.count()}


# ──────────── Trades ────────────

@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    strategy_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Trade).order_by(Trade.id.desc())
    if strategy_id:
        q = q.filter(Trade.strategy_id == strategy_id)
    trades = q.offset((page - 1) * page_size).limit(page_size).all()
    return trades


@router.get("/trades/count")
def trades_count(strategy_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Trade)
    if strategy_id:
        q = q.filter(Trade.strategy_id == strategy_id)
    return {"count": q.count()}


@router.post("/trades/sync-fills")
def sync_fills_now(db: Session = Depends(get_db)):
    from app.fill_ledger import sync_demo_fills
    from app.runtime_status import record
    try:
        result = sync_demo_fills(db)
        record("fills", True, result["message"])
        return result
    except ValueError as exc:
        record("fills", False, str(exc))
        raise HTTPException(409, str(exc)) from None
    except Exception:
        db.rollback()
        message = "成交同步失败，本地历史已保留；请检查模拟盘凭据、网络及接口状态"
        record("fills", False, message)
        raise HTTPException(502, message) from None


# ──────────── Positions ────────────

@router.get("/positions", response_model=list[PositionOut])
def list_positions(db: Session = Depends(get_db)):
    return db.query(Position).all()


@router.get("/positions/live", response_model=list[PositionOut])
def list_positions_live(db: Session = Depends(get_db)):
    """Realtime positions for UI: sync from exchange then return latest snapshot."""
    if not sync_positions():
        raise HTTPException(502, "同步失败，原持仓记录已保留；请查看运行状态")
    return db.query(Position).all()


@router.post("/positions/sync")
def sync_positions_now():
    """Manually sync positions from OKX."""
    try:
        if not sync_positions():
            from app.runtime_status import snapshot
            return JSONResponse({"detail": snapshot().get("positions", {}).get("message", "同步失败，原记录已保留")}, status_code=502)
        return {"message": "持仓同步完成，已更新本地记录"}
    except Exception as e:
        raise HTTPException(500, f"同步失败: {str(e)}")


@router.post("/positions/close")
def manual_close(data: ManualCloseRequest, db: Session = Depends(get_db)):
    """Manually close a position."""
    # Find position
    pos = db.query(Position).filter(
        Position.symbol == data.symbol,
        Position.side == data.side,
    ).first()

    strategy_id = None
    entry_price = 0.0

    if not pos or pos.size <= 0:
        # Try fetching from exchange directly
        exchange_pos = fetch_positions()
        target = None
        for p in exchange_pos:
            if p.get("symbol") == data.symbol and p.get("side") == data.side:
                target = p
                break
        if not target:
            raise HTTPException(404, "未找到该持仓")
        amount = _to_float(target.get("contracts"), 0.0)
        entry_price = _to_float(target.get("entryPrice"), 0.0)
    else:
        amount = pos.size
        entry_price = _to_float(pos.avg_price, 0.0)
        strategy_id = pos.strategy_id

    if amount <= 0:
        raise HTTPException(400, "持仓数量无效，无法平仓")

    if strategy_id is None:
        matched_open = db.query(Trade).filter(
            Trade.action == "open",
            Trade.symbol == data.symbol,
            Trade.side == data.side,
        ).order_by(Trade.created_at.desc()).first()
        if matched_open:
            strategy_id = matched_open.strategy_id

    if strategy_id is None:
        matched_any = db.query(Trade).filter(
            Trade.action == "open",
            Trade.symbol == data.symbol,
        ).order_by(Trade.created_at.desc()).first()
        if matched_any:
            strategy_id = matched_any.strategy_id

    try:
        order = exchange_close_position(data.symbol, data.side, amount)
        order_dict = _as_dict(order)
        trade_recorded = False
        warning = ""

        if strategy_id is not None:
            close_price = _to_float(order_dict.get("price"), 0.0) or _to_float(order_dict.get("average"), 0.0) or entry_price


            trade = Trade(
                strategy_id=strategy_id,
                symbol=data.symbol,
                side=data.side,
                action="close",
                price=close_price,
                quantity=amount,
                order_id=order_dict.get("id", ""),
                pnl=None,
                status="submitted",
                fee=_fee_cost(order_dict),
            )
            db.add(trade)
            db.commit()
            trade_recorded = True
        else:
            warning = "已平仓，但未找到对应策略，未写入交易记录"

        # Sync positions after close
        sync_positions()
        return {
            "message": f"已提交平仓请求 {data.symbol} {data.side}，成交结果以成交同步为准",
            "order_id": order_dict.get("id", ""),
            "trade_recorded": trade_recorded,
            "warning": warning,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"平仓失败: {str(e)}")


# ──────────── Equity ────────────

@router.get("/equity", response_model=list[EquitySnapshotOut])
def list_equity(
    limit: int = Query(288, ge=1, le=10000),  # default ~24h at 5min intervals
    db: Session = Depends(get_db),
):
    return db.query(EquitySnapshot).order_by(
        EquitySnapshot.timestamp.desc()
    ).limit(limit).all()[::-1]


@router.get("/runtime/status")
def runtime_status():
    from app.runtime_status import snapshot
    return snapshot()
