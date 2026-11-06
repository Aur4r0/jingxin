# 静心 · 个人交易工作台

基于 FastAPI、SQLite、APScheduler 和 ccxt 的个人交易研究项目。提供简约日夜界面、账户概览、策略管理、持仓与交易记录、执行日志及 Telegram 开仓通知。

源自 [GhostWolfLab/PointPivot](https://github.com/GhostWolfLab/PointPivot)，保留原项目 MIT 许可证。当前版本面向模拟交易学习，不承诺收益。

## 支持范围

| 功能 | 状态 |
|---|---|
| OKX 永续合约模拟盘 / 实盘 | 已接入；首次验证使用模拟盘 |
| 币安 U 本位合约模拟盘 / 实盘 | 仅保存配置与只读测试，不执行策略 |
| 现货 | 不支持 |
| AI 决策与规则模式 | 已有实现，未提供收益验证 |
| Telegram | 开仓通知与测试消息 |
| Linux VPS | Docker Compose / systemd，单实例 |

## 页面介绍

| 页面 | 用途 |
|---|---|
| 概览 | 账户权益、可用余额、持仓盈亏、净值曲线和最近执行；区分页面读取时间与记录时间 |
| 策略 | 创建与编辑交易策略，手动启停或单次执行；提示词模板位于次级标签 |
| 持仓与交易 | 当前合约仓位及手动平仓，切换查看历史交易；同步失败保留旧记录 |
| 运行记录 | 筛选执行记录，查看决策、订单状态与错误；提示词和 AI 响应折叠并支持复制 |
| 设置 | OKX 账户、币安只读配置、AI、Telegram 及高级连接设置，分区独立保存 |

界面支持日间/夜间主题和窄屏布局。监控页可自动刷新，切到后台暂停；刷新失败保留上次数据并提示异常。实盘操作具有确认提示，但不能替代交易所核对和人工风控。

## Windows 双击配置

1. 安装 Python 3.12 **64 位**，包含 Python Launcher，或勾选 Add Python to PATH。
2. 下载源码并完整解压到自己有写入权限的目录。
3. 双击 `setup-windows.cmd`，自动创建环境、安装依赖，并提示设置管理员账号和密码。
4. 配置成功后双击 `start-windows.cmd`，浏览器访问 `http://127.0.0.1:8000`。

配置脚本不会启动策略、下单、下载 Python 安装器或更改系统执行策略。已有 `.env` 和数据库保留；迁移过来的 `.venv` 不会自动删除。若检测到不兼容环境，请只重命名 `.venv` 后重试。Python 下载失败或安装依赖失败时，按提示处理后重新运行。

启动会恢复已有启用策略，升级或迁移前先暂停策略。窗口关闭后服务不会继续运行；长期托管请使用 VPS 部署方案。

## 本地快速开始

需要 Python 3.12。下载或克隆本仓库后：

```sh
git clone https://github.com/Aur4r0/jingxin.git
cd jingxin
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/setup.py
.venv/bin/python run.py
```

Windows 使用 `.venv\Scripts\python` 和 `.venv\Scripts\pip`。浏览器访问 `http://127.0.0.1:8000`，使用初始化时设置的账号。没有公开默认密码，初始化不会创建交易策略。需要重设账号时运行 `python scripts/setup.py --reset-admin`，加密密钥保持不变。

1. 设置 → 配置 OKX **模拟盘**的 API Key、Secret Key、Passphrase，保存后测试连接。
2. 配置 AI 服务与模型、按需配置 Telegram 并发送测试消息。
3. 创建策略默认暂停；检查参数和环境后，单次模拟执行，再查看运行记录和交易所持仓/保护单。
4. 确认符合预期后才人工启用定时运行。立即执行可能提交订单；暂停不会平仓。

页面自动刷新只读取本地数据库。后台持仓约每 2 分钟同步，账户净值约每 5 分钟记录；页面更新时间不等于交易所数据时间。同步失败保留原持仓，监控页面显示运行错误。

## 配置和数据

- `.env` 保存管理员密码哈希、会话密钥、数据库加密密钥。
- `trading.db` 保存策略、账户配置及历史记录；API 凭据加密存储。
- 数据库和 `ENCRYPTION_KEY` 必须配套备份，不要更换已有密钥。
- 服务启动会重新加载已启用策略；迁移前务必暂停策略。

## 部署、测试与发布

- [VPS 部署、迁移和备份](docs/DEPLOY.md)
- [安全与发布检查](SECURITY.md)
- Python 回归测试：`.venv/bin/python -m unittest discover -s tests -v`。前端脚本检查需要 Node.js 20+；测试不应使用实盘密钥。
- 不要上传 `.env`、数据库、备份或个人日志。发布自己的 GitHub 仓库前检查暂存区。

## 常用运维工具

```sh
python scripts/doctor.py             # 离线检查配置与数据库，不调用交易所
python scripts/backup.py             # 数据库一致性备份与配套密钥备份
python scripts/restore.py backups/备份目录 /新的恢复目录
python scripts/release_check.py      # Git 发布候选路径检查，不推送
```

恢复只允许新目录，默认暂停全部策略，原备份不变。检查通过不代表策略收益或外部接口可用；日志与备份仍需人工核对。

## 项目结构

`app/` 后端与调度；`templates/` 页面；`static/` 样式与交互；`tests/` 回归测试；`scripts/` 初始化和备份；`deploy/` 服务模板。

## 风险说明

仅用于技术研究，不构成投资建议。网络、模型响应、交易所订单及保护单均可能失败。当前仍需人工监督，缺少完整订单幂等恢复和多实例协调，实盘使用前必须独立验证。
