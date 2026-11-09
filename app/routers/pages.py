"""Page routes - serve Jinja2 templates"""

import json
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models import (
    Strategy, StrategyLog, Trade, Position, EquitySnapshot, SystemConfig, get_db,
)
from app.routers.strategies import DEFAULT_PROMPT_TEMPLATE

router = APIRouter(tags=["pages"])

from app.config import settings
from app.security import verify_password

LOGIN_USERNAME = settings.app_username

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ─── Template helpers ────────────────────────────────

def _action_badge_class(action: str) -> str:
    mapping = {
        "long": "badge badge-action-long",
        "short": "badge badge-action-short",
        "close_long": "badge badge-action-close_long",
        "close_short": "badge badge-action-close_short",
        "hold": "badge badge-action-hold",
    }
    return mapping.get(action, "badge bg-light text-dark")


def _action_label(action: str) -> str:
    mapping = {
        "long": "做多", "short": "做空",
        "close_long": "平多", "close_short": "平空",
        "hold": "持有",
    }
    return mapping.get(action, action or "-")


def _strategy_name_map(db: Session) -> dict:
    strategies = db.query(Strategy.id, Strategy.name).all()
    return {s.id: s.name for s in strategies}


def _fmt_bj_time(dt: datetime | None, fmt: str = "%m-%d %H:%M:%S") -> str:
    """Format datetime as Beijing time (Asia/Shanghai)."""
    if not dt:
        return "-"
    # Stored DB time is treated as UTC when tzinfo is absent.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    bj = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    return bj.strftime(fmt)


# ─── Page Routes ─────────────────────────────────────

@router.get("/login")
def login_page(request: Request, next: str = "/overview"):
    if request.session.get("user") == LOGIN_USERNAME:
        return RedirectResponse(url=next or "/overview", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next or "/overview",
        "error": "",
    })


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/strategies"),
):
    if LOGIN_USERNAME and username == LOGIN_USERNAME and verify_password(password, settings.app_password_hash):
        request.session["user"] = LOGIN_USERNAME
        safe_next = next if next.startswith("/") and not next.startswith("//") and "\\" not in next else "/overview"
        return RedirectResponse(url=safe_next or "/overview", status_code=303)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next or "/overview",
        "error": "用户名或密码错误",
    }, status_code=400)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.get("/")
def index():
    return RedirectResponse(url="/overview")


@router.get("/strategies")
def strategies_page(request: Request, db: Session = Depends(get_db)):
    all_strategies = db.query(Strategy).order_by(Strategy.id.desc()).all()
    # Decode symbols JSON for template
    for s in all_strategies:
        if not hasattr(s, '_symbols_cache'):
            s._symbols_cache = s.symbols  # uses the @property
    return templates.TemplateResponse("strategies.html", {
        "request": request,
        "active_page": "strategies",
        "strategies": all_strategies,
    })


@router.get("/strategies/new")
def strategy_new_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("strategy_edit.html", {
        "request": request,
        "active_page": "strategies",
        "is_new": True,
        "strategy": None,
        "default_prompt": DEFAULT_PROMPT_TEMPLATE,
    })


@router.get("/strategies/{strategy_id}/edit")
def strategy_edit_page(strategy_id: int, request: Request, db: Session = Depends(get_db)):
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not s:
        return RedirectResponse(url="/strategies")

    # Prepare a view-friendly object
    class StrategyView:
        pass
    sv = StrategyView()
    sv.id = s.id
    sv.name = s.name
    sv.enabled = s.enabled
    sv.position_usdt = s.position_usdt
    sv.use_ai = s.use_ai
    sv.ai_provider = s.ai_provider or ""
    sv.ai_base_url = s.ai_base_url or ""
    sv.ai_model = s.ai_model or ""
    sv.has_api_key = bool(s.ai_api_key_enc)
    sv.prompt_template = s.prompt_template
    sv.symbols = s.symbols
    sv.interval_minutes = s.interval_minutes
    sv.max_position_pct = s.max_position_pct
    sv.leverage = s.leverage
    sv.take_profit_pct = s.take_profit_pct
    sv.stop_loss_pct = s.stop_loss_pct
    sv.scan_enabled = s.scan_enabled or False
    sv.scan_top_n = s.scan_top_n or 5
    sv.scan_min_change_pct = s.scan_min_change_pct or 3.0
    sv.scan_min_volume_usdt = s.scan_min_volume_usdt or 500000
    try:
        sv.scan_exclude_symbols = json.loads(s.scan_exclude_symbols or "[]")
    except (json.JSONDecodeError, TypeError):
        sv.scan_exclude_symbols = []

    return templates.TemplateResponse("strategy_edit.html", {
        "request": request,
        "active_page": "strategies",
        "is_new": False,
        "strategy": sv,
        "default_prompt": DEFAULT_PROMPT_TEMPLATE,
    })


@router.get("/logs")
def logs_page(
    request: Request,
    strategy_id: int | None = None,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    page_size = 20
    q = db.query(StrategyLog).order_by(StrategyLog.id.desc())
    if strategy_id:
        q = q.filter(StrategyLog.strategy_id == strategy_id)
    total = q.count()
    total_pages = max(1, math.ceil(total / page_size))
    logs = q.offset((page - 1) * page_size).limit(page_size).all()

    strategies = db.query(Strategy).order_by(Strategy.id.desc()).all()
    strategy_names = _strategy_name_map(db)

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "active_page": "logs",
        "logs": logs,
        "strategies": strategies,
        "strategy_names": strategy_names,
        "filter_strategy_id": strategy_id,
        "page": page,
        "total_pages": total_pages,
        "action_badge_class": _action_badge_class,
        "action_label": _action_label,
        "fmt_bj_time": _fmt_bj_time,
    })


@router.get("/positions")
def positions_page(request: Request, db: Session = Depends(get_db)):
    positions = db.query(Position).all()
    strategy_names = _strategy_name_map(db)

    cfg = db.query(SystemConfig).first()
    is_simulated = bool(cfg.okx_simulated) if cfg else True

    equity_data = db.query(EquitySnapshot).order_by(
        EquitySnapshot.timestamp.desc()
    ).limit(288).all()[::-1]

    equity_json = json.dumps([
        {"timestamp": e.timestamp.isoformat(), "total_equity": e.total_equity}
        for e in equity_data
    ])

    return templates.TemplateResponse("positions.html", {
        "request": request,
        "active_page": "positions",
        "positions": positions,
        "strategy_names": strategy_names,
        "equity_data": equity_data,
        "equity_json": equity_json,
        "is_simulated": is_simulated,
    })


@router.get("/trades")
def trades_page(
    request: Request,
    strategy_id: int | None = None,
    page: int = Query(1, ge=1),
    source: str = "fills",
    db: Session = Depends(get_db),
):
    from app.fill_ledger import account_key, fill_summary, fill_view
    from app.models import ExecutionFill
    from app.runtime_status import snapshot
    page_size = 50
    if source not in ("fills", "legacy"):
        source = "fills"
    error = ""
    views, summary = [], None
    legacy_q = db.query(Trade)
    if strategy_id:
        legacy_q = legacy_q.filter(Trade.strategy_id == strategy_id)
    legacy_count = legacy_q.count()
    if source == "legacy":
        total = legacy_count
        trades = legacy_q.order_by(Trade.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    else:
        trades = []
        try:
            scope = account_key(db.query(SystemConfig).first())
            q = db.query(ExecutionFill).filter(ExecutionFill.environment == "demo", ExecutionFill.account_key == scope)
            # 当前成交不能可靠归属策略，不把账户级数据当作策略盈亏。
            if strategy_id:
                error = "成交尚未可靠归属策略；请清除策略筛选查看账户成交，旧记录可在另一标签查看"
                total = 0
            else:
                total = q.count()
                summary = fill_summary(q.yield_per(500)) if total else None
                rows = q.order_by(ExecutionFill.filled_at.desc(), ExecutionFill.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
                views = [fill_view(row) for row in rows]
        except ValueError as exc:
            error = str(exc)
            total = 0
        except RuntimeError:
            error = "无法解密模拟盘配置，请检查配套加密密钥"
            total = 0
    return templates.TemplateResponse("trades.html", {
        "request": request, "active_page": "trades", "trades": trades, "fills": views,
        "source": source, "summary": summary, "ledger_error": error,
        "sync_status": snapshot().get("fills", {}),
        "strategies": db.query(Strategy).order_by(Strategy.id.desc()).all(),
        "strategy_names": _strategy_name_map(db), "filter_strategy_id": strategy_id,
        "page": page, "total_pages": max(1, math.ceil(total / page_size)),
        "total": total, "legacy_count": legacy_count,
    })


@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    cfg = db.query(SystemConfig).first()
    if not cfg:
        cfg = SystemConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    class ConfigView:
        pass
    cv = ConfigView()
    cv.okx_live_api_key_set = bool(cfg.okx_api_key_enc)
    cv.okx_live_secret_key_set = bool(cfg.okx_secret_key_enc)
    cv.okx_live_passphrase_set = bool(cfg.okx_passphrase_enc)
    cv.okx_sim_api_key_set = bool(cfg.okx_sim_api_key_enc)
    cv.okx_sim_secret_key_set = bool(cfg.okx_sim_secret_key_enc)
    cv.okx_sim_passphrase_set = bool(cfg.okx_sim_passphrase_enc)
    cv.binance_live_api_key_set = bool(cfg.binance_live_api_key_enc)
    cv.binance_live_secret_key_set = bool(cfg.binance_live_secret_key_enc)
    cv.binance_sim_api_key_set = bool(cfg.binance_sim_api_key_enc)
    cv.binance_sim_secret_key_set = bool(cfg.binance_sim_secret_key_enc)
    cv.binance_proxy = cfg.binance_proxy or ""
    cv.okx_simulated = cfg.okx_simulated
    cv.okx_proxy = cfg.okx_proxy or ""
    cv.tg_bot_token_set = bool(cfg.tg_bot_token_enc)
    cv.tg_chat_id = cfg.tg_chat_id or ""
    cv.tg_proxy = cfg.tg_proxy or ""
    cv.ai_default_provider = cfg.ai_default_provider or "deepseek"
    cv.ai_default_api_key_set = bool(cfg.ai_default_api_key_enc)
    cv.ai_default_base_url = cfg.ai_default_base_url or ""
    cv.ai_default_model = cfg.ai_default_model or "deepseek-chat"

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "active_page": "settings",
        "config": cv,
    })


@router.get("/prompt-templates")
def prompt_templates_page(request: Request):
    return templates.TemplateResponse("prompt_templates.html", {
        "request": request,
        "active_page": "prompt_templates",
    })


templates.env.filters["bj_time"] = _fmt_bj_time
templates.env.filters["action_label"] = _action_label


@router.get("/overview")
def overview_page(request: Request, db: Session = Depends(get_db)):
    snapshots = db.query(EquitySnapshot).order_by(EquitySnapshot.timestamp.desc()).limit(288).all()[::-1]
    positions = db.query(Position).all()
    strategies = db.query(Strategy).all()
    logs = db.query(StrategyLog).order_by(StrategyLog.created_at.desc()).limit(5).all()
    latest = snapshots[-1] if snapshots else None
    return templates.TemplateResponse("overview.html", {
        "request": request, "active_page": "overview", "latest": latest,
        "positions": positions, "strategy_count": len(strategies),
        "enabled_count": sum(bool(s.enabled) for s in strategies),
        "pnl": sum(p.unrealized_pnl or 0 for p in positions),
        "logs": logs, "strategy_names": {s.id: s.name for s in strategies},
        "chart_data": [{"time": s.timestamp.isoformat() + "Z", "equity": s.total_equity} for s in snapshots],
        "position_time": max((p.updated_at for p in positions if p.updated_at), default=None),
    })
