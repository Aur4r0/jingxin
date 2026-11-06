"""OKX AI Auto-Trading System - Main Application"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.models import init_db
from app.engine import start_scheduler, stop_scheduler
from app.routers import strategies, trading, system, pages, prompt_templates

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
# HTTP 客户端日志可能包含 Telegram Token，默认不输出请求地址。
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.app_username or not settings.app_password_hash or not settings.app_session_secret or not settings.encryption_key:
        raise RuntimeError("缺少安全配置，请先运行 python scripts/setup.py")
    # 同一工作目录只允许一个应用实例，防止重复调度。
    from app.instance_lock import acquire
    lock = acquire()
    # Startup
    logger.info("Initializing database...")
    init_db()
    logger.info("Starting scheduler...")
    start_scheduler()
    logger.info("System ready")
    try:
        yield
    finally:
        logger.info("Stopping scheduler...")
        stop_scheduler()
        lock.close()


app = FastAPI(
    title="静心交易工作台",
    version="1.0.0",
    lifespan=lifespan,
)


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    login_attempts = {}
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            if origin:
                from urllib.parse import urlsplit
                if urlsplit(origin).netloc != request.headers.get('host'):
                    return JSONResponse({'detail': '请求来源不匹配'}, status_code=403)
        if path == '/login' and request.method == 'POST':
            import time
            from collections import deque
            address = request.client.host if request.client else 'unknown'
            now = time.monotonic()
            attempts = self.login_attempts.setdefault(address, deque())
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 10:
                return JSONResponse({'detail': '登录尝试过于频繁，请一分钟后重试'}, status_code=429)
            attempts.append(now)
            if len(self.login_attempts) > 4096:
                self.login_attempts = {k:v for k,v in self.login_attempts.items() if v and v[-1] > now-60}

        public_paths = {
            "/login",
            "/logout",
            "/api/health",
        }
        if path in public_paths or path.startswith("/static/"):
            return await call_next(request)

        if request.session.get("user") == pages.LOGIN_USERNAME:
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse({"detail": "未登录或登录已失效"}, status_code=401)

        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


app.add_middleware(
    AuthRequiredMiddleware,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_session_secret or "not-initialized-no-service",
    same_site="lax",
    https_only=settings.app_cookie_secure,
)

# Static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# API routes
app.include_router(strategies.router)
app.include_router(trading.router)
app.include_router(system.router)
app.include_router(prompt_templates.router)

# Page routes (Jinja2 templates)
app.include_router(pages.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
