"""币安 U 本位合约账户只读连接，不复用 OKX 交易适配器。"""
import ccxt


def build_client(api_key: str, secret: str, simulated: bool, proxy: str):
    client = ccxt.binanceusdm({
        "apiKey": api_key, "secret": secret,
        "enableRateLimit": True, "timeout": 10000,
    })
    if simulated:
        client.set_sandbox_mode(True)
        # 当前币安 Demo 地址与项目锁定版本的 ccxt 默认测试地址不同。
        for name, url in list(client.urls["api"].items()):
            if name.startswith("fapi"):
                suffix = url.split("/fapi/", 1)[1] if "/fapi/" in url else None
                client.urls["api"][name] = "https://demo-fapi.binance.com/fapi/" + suffix if suffix else "https://demo-fapi.binance.com/futures/data"
    client.session.trust_env = False
    if proxy:
        client.session.proxies = {"http": proxy, "https": proxy}
    return client


def read_account(api_key: str, secret: str, simulated: bool, proxy: str):
    client = build_client(api_key, secret, simulated, proxy)
    try:
        # 原始只读接口，不加载现货市场，也不验证交易权限。
        return client.fapiPrivateV2GetAccount()
    finally:
        client.session.close()
