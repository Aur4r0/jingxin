# VPS 部署与迁移

## 方案 A：Docker Compose

先安装 Docker Engine 与 Compose 插件。源码目录执行：

```sh
docker compose build
# 使用容器内 Python 初始化，VPS 不需要额外安装 Python 依赖。
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace --entrypoint python \
  jingxin:local scripts/setup.py
mkdir -p data
sudo chown 10001:10001 data
sudo chown "$(id -u):10001" .env
sudo chmod 640 .env
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 jingxin
```

项目源码与 `.env` 位于根目录；容器数据库持久化到 `data/trading.db`，容器不以 root 运行。不要使用 `--scale`。健康检查仅表示 Web 服务响应，不代表交易所、AI 或策略正常，也不会自动重启 unhealthy 容器；进程退出由 restart 策略处理。

从自己电脑访问 VPS：

```sh
ssh -N -L 8000:127.0.0.1:8000 USER@VPS_IP
```

浏览器访问 `http://127.0.0.1:8000`。如果本地已占用 8000，隧道改为 `-L 8001:127.0.0.1:8000`，浏览器访问 8001。

容器中的 `127.0.0.1:7890` 不是电脑或宿主机代理。必须使用容器可访问的代理，或在可直连环境留空；不要为了连接关闭 TLS 校验。首次进入页面配置模拟盘账户、AI 和 Telegram，然后验证只读连接及单次模拟执行。

## 方案 B：systemd

适用于已安装 Python 3.12 的 Linux。创建专用系统用户 `jingxin`，将代码放在 `/opt/jingxin`，目录由该用户拥有。以该用户创建虚拟环境、安装依赖并运行初始化脚本。将 `deploy/jingxin.service` 复制到 `/etc/systemd/system/`：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now jingxin
sudo systemctl status jingxin
sudo journalctl -u jingxin -n 100 --no-pager
```

数据库位于 `/opt/jingxin/trading.db`。不要同时启动 Docker 和 systemd 两套部署。

## 迁移已有配置

1. 在原系统暂停全部策略，等待执行中的任务结束，再停止原服务。暂停不平仓，原有订单和持仓需人工核对。
2. 使用 `python scripts/backup.py` 生成数据库一致性备份和配套 `.env`。不要只复制正在运行的 SQLite 主文件。
3. 使用 SSH/SCP 传输本地修改后的完整代码和备份，不要依赖上游 GitHub 中尚无本地修改的代码。
4. Docker 部署：备份的数据库放在 `data/trading.db`，备份 `.env` 放根目录；systemd 部署二者都放工作目录。保留原 `ENCRYPTION_KEY`，不要重新生成。
5. 旧 `.env` 没有登录哈希和会话密钥时运行初始化脚本补齐；已有加密密钥保留。如配置行存在但值为空，应先备份再删除该空行后初始化。
6. 迁移已有弱密码时，用初始化脚本的 `--reset-admin` 参数重新设置管理员（不更换加密密钥），再重启服务。
7. 修正文件所有者/权限、代理和 API 出口 IP 白名单。先验证账户、AI、Telegram，再人工启用策略。原设备不要再次启动同一策略。

## 备份、升级与恢复

本地/systemd：`python scripts/backup.py`。Docker：在宿主机使用 `python scripts/backup.py --database data/trading.db --env .env`。

备份包含密钥，不要上传公开仓库。更新前先暂停策略、停止服务并备份；再更新代码、安装依赖或重建镜像。启动会执行缺失字段迁移，暂不支持自动向下迁移。回滚时恢复匹配版本的代码、数据库和 `.env`，不可把新数据库直接交给旧代码。恢复必须停止服务，禁止覆盖运行中的 SQLite 文件。定期在独立环境验证备份可解密且策略保持暂停。

## 当前边界

- 自动交易只支持 OKX 永续合约；币安仅支持凭据保存和只读连接测试，现货未接入。
- Telegram 当前主要是开仓通知，不等于完整故障告警系统。
- 尚未实现跨主机分布式锁或交易所订单幂等恢复，不适合多实例或无人值守高可用部署。
- 本仓库锁定了现有依赖版本，公开生产使用前还需完成依赖安全升级验证与 HTTPS/访问控制配置。

## 部署前检查与安全恢复

执行 `python scripts/doctor.py` 离线检查配置、数据库完整性和凭据能否解密，不会访问交易所。Docker 数据库在宿主机时加 `--database data/trading.db`。

执行 `python scripts/restore.py backups/备份目录 /新的恢复目录`。目标必须不存在，校验通过才恢复，并自动暂停所有策略；不会覆盖现有数据或启动服务。恢复后依照上面的迁移流程人工安装和验证。

发布前执行 `python scripts/release_check.py`，再人工审查暂存区和历史提交。该检查只检查路径，不能代替秘密扫描。

服务关闭会等待执行中的后台任务结束。遇到长时间网络等待时应先检查日志，不要反复启动或直接复制运行中的数据库。
