"""安全错误分类，不向页面暴露签名请求或凭据。"""
import ccxt


def explain(error):
    if isinstance(error, ccxt.AuthenticationError):
        return '凭据校验失败，请检查密钥、API 口令及实盘/模拟盘环境'
    if isinstance(error, ccxt.PermissionDenied):
        return '账户权限不足，请检查 API 权限与 IP 白名单'
    if isinstance(error, ccxt.RateLimitExceeded):
        return '交易所请求限流，请稍后重试'
    if isinstance(error, ccxt.NetworkError):
        return '连接交易所失败，请检查网络、代理与服务器时间'
    return '交易所读取失败，请检查配置与服务状态'
