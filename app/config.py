"""OKX AI Auto-Trading System - Configuration"""

import os
from pydantic_settings import BaseSettings
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    # OKX
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_simulated: bool = True

    # AI defaults
    ai_default_provider: str = "deepseek"
    ai_default_api_key: str = ""
    ai_default_base_url: str = "https://api.deepseek.com/v1"

    # Encryption
    encryption_key: str = ""

    app_username: str = ""
    app_password_hash: str = ""
    app_session_secret: str = ""
    app_cookie_secure: bool = False

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def get_fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise RuntimeError("缺少 ENCRYPTION_KEY，请先运行 python scripts/setup.py")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plain: str) -> str:
    if not plain:
        return ""
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return get_fernet().decrypt(encrypted.encode()).decode()
    except Exception as exc:
        raise RuntimeError("无法解密配置，请恢复与数据库配套的 ENCRYPTION_KEY") from exc
