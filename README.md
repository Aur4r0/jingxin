# 静心 · 个人交易工作台

静心是一个用于研究和管理个人交易策略的 Web 工具，提供账户概览、策略管理、持仓记录、运行日志和 Telegram 开仓通知。

项目源自 [GhostWolfLab/PointPivot](https://github.com/GhostWolfLab/PointPivot)，保留原项目 MIT 许可证。当前版本适合学习和模拟交易，不能保证收益。

## 先看这三件事

1. 自动交易目前只支持 OKX 永续合约。
2. 币安只保存配置并做只读连接测试，暂不执行策略和下单。
3. 现货暂不支持。

## 最快开始

### Windows

1. 安装 Python 3.12 64 位：<https://www.python.org/downloads/windows/>。
2. 下载并解压项目，双击 `setup-windows.cmd`。
3. 按提示设置管理员账号和密码。
4. 双击 `start-windows.cmd`，打开 <http://127.0.0.1:8000>。

脚本会自动创建虚拟环境、安装依赖和初始化配置，不会启动策略或自动下单。关闭窗口，服务就会停止。长期运行请使用 VPS。

### macOS / Linux 本地运行

```sh
git clone https://github.com/Aur4r0/jingxin.git
cd jingxin
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/setup.py
.venv/bin/python run.py
```

然后打开 <http://127.0.0.1:8000>，使用初始化时设置的账号登录。

### VPS 运行

VPS 推荐使用 Docker Compose。直接执行：

```sh
git clone https://github.com/Aur4r0/jingxin.git
cd jingxin
docker compose build
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace --entrypoint python \
  jingxin:local scripts/setup.py
mkdir -p data
sudo chown 10001:10001 data
sudo chown "$(id -u):10001" .env
sudo chmod 640 .env
docker compose up -d
```

查看状态：

```sh
docker compose ps
docker compose logs --tail=100 jingxin
```

从自己的电脑访问 VPS：

```sh
ssh -N -L 8000:127.0.0.1:8000 用户名@VPS_IP
```

再打开 <http://127.0.0.1:8000>。完整迁移、备份和 systemd 方案见 [VPS 部署说明](docs/DEPLOY.md)。

## 首次配置

登录后按这个顺序操作：

1. 设置 → OKX：填入模拟盘 API Key、Secret Key、Passphrase，保存并测试连接。
2. 设置 → AI：填写兼容 OpenAI 接口的地址、密钥和模型。
3. 设置 → Telegram：填写 Bot Token 和 Chat ID，发送测试消息。
4. 策略：新建策略，先保持暂停，执行一次模拟测试。
5. 查看运行记录、持仓和交易所保护单，确认无误后再手动启用定时运行。

实盘前请先用模拟盘验证。启用策略后，服务启动会恢复定时执行；暂停策略不会自动平仓。

## 页面说明

| 页面 | 作用 |
| --- | --- |
| 概览 | 查看账户权益、余额、持仓盈亏、净值曲线和最近执行 |
| 策略 | 新建、编辑、暂停或启用策略；管理提示词模板 |
| 持仓与交易 | 查看当前仓位、历史交易和手动平仓入口 |
| 运行记录 | 查看执行结果、订单状态、错误和 AI 原始响应 |
| 设置 | 配置 OKX、币安只读连接、AI、Telegram 和高级选项 |

页面支持日间和夜间主题。自动刷新只读取本地数据库；交易所同步失败时会保留上一次持仓记录并显示错误。

## 数据和安全

- `.env` 保存登录哈希、会话密钥和数据库加密密钥，不能上传到 GitHub。
- `trading.db` 保存策略、账户配置和历史记录，API 凭据以加密形式保存。
- 数据库和 `ENCRYPTION_KEY` 必须一起备份，不能随意更换密钥。
- 不要同时启动两套服务，也不要把数据库文件复制到正在运行的服务中。

常用检查命令：

```sh
python scripts/doctor.py
python scripts/backup.py
python scripts/restore.py backups/备份目录 /新的恢复目录
```

## 测试

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试只使用隔离配置，不应填入真实交易所密钥。

## 风险边界

本项目仅用于技术研究，不构成投资建议。网络、模型、交易所订单和保护单都可能失败；当前没有完整的订单幂等恢复和多实例协调能力，实盘必须人工监督。

## 项目结构

`app/` 后端与调度；`templates/` 页面；`static/` 前端资源；`tests/` 测试；`scripts/` 初始化、备份和恢复；`deploy/` 服务模板。

## 模拟盘异常对账

已有成交、仓位或保护单不一致时，请先暂停策略，按 [只读对账步骤](docs/RECONCILIATION.md) 核对。该工具不修改订单，也不代表在线交易流程已修复。

### 本批修复进展

新增模拟盘只读对账：核对真实成交、仓位单位、费用和遗留保护单，离线测试共 34 项通过。**在线仓位限额与保护单生命周期尚未修复，请保持策略暂停并人工核对。成交账本进展见下方。**

完整范围与限制见 [更新记录](CHANGELOG.md)。

## 成交与盈亏记录更新

历史交易新增交易所成交账本，展示逐笔实际成交价、张数、已实现盈亏、手续费及净盈亏；顶部统计当前模拟盘 API 配置与日期、交易对筛选范围内的全部已同步记录，不受分页影响。旧订单单独保留，不参与确认盈亏统计。

- 当前仅支持模拟盘，后台每两分钟同步，也可手动同步。
- 默认读取最近七天，已入库的更早记录保留。首次同步不等于导入完整历史。
- 不含资金费；成交尚未可靠归属策略，不提供策略级收益或胜率比较。
- 缺失或非 USDT 费用不当作零，完整净盈亏显示为待核实。
- 更新前先人工暂停策略并备份数据库和配套 `.env`；新增成交表不删除旧记录。

详情见 [成交同步与统计口径](docs/FILL_LEDGER.md)。在线仓位限额、订单幂等恢复及保护单生命周期仍待修复，暂不恢复无人监督自动交易。

## 历史交易面板

- 按今天、昨天、最近7天、最近30天、自定义日期区间和交易对筛选，统一使用北京时间。
- 展示已实现盈亏、手续费净支出、净交易盈亏，并补充扣款、返佣、成交计数和待核实数量。
- 每日盈亏柱状图与筛选一致；明细默认每页10条，可折叠并切换20/50条，长订单号移入详情。
- 日间、夜间和手机布局均已适配，不新增第三方 UI 运行依赖。

选择更长日期不会自动补取更早成交；无记录不等于没有交易，资金费和浮动盈亏未纳入。字段映射、统计口径、接口参数和更新步骤见 [历史交易页面说明](docs/TRADE_DASHBOARD.md)。
