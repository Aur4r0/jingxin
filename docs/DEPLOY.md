# VPS 部署说明

只想跑起来，选 Docker Compose。需要自己管理 Python 服务，再看 systemd。

## 方案一：Docker Compose

### 1. 安装 Docker

在 VPS 安装 Docker Engine 和 Compose 插件。确认命令可用：

```sh
docker --version
docker compose version
```

### 2. 下载项目

```sh
git clone https://github.com/Aur4r0/jingxin.git
cd jingxin
```

### 3. 初始化账号

先构建镜像，再运行一次初始化脚本：

```sh
docker compose build
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace --entrypoint python \
  jingxin:local scripts/setup.py
```

按提示输入登录账号和密码。脚本只写入配置，不会启动策略。

### 4. 启动

```sh
mkdir -p data
sudo chown 10001:10001 data
sudo chown "$(id -u):10001" .env
sudo chmod 640 .env
docker compose up -d
docker compose ps
```

看到容器状态为 `Up` 后，查看日志：

```sh
docker compose logs --tail=100 jingxin
```

### 5. 打开页面

默认只监听 VPS 本机，推荐使用 SSH 隧道：

```sh
ssh -N -L 8000:127.0.0.1:8000 用户名@VPS_IP
```

本地浏览器打开 <http://127.0.0.1:8000>。如果本地 8000 被占用，把左侧端口改成 8001，并访问 8001。

### 6. 页面内配置

按顺序操作：

1. 设置 OKX 模拟盘并测试连接。
2. 设置 AI，并确认能正常返回结果。
3. 设置 Telegram，发送测试消息。
4. 新建策略，保持暂停，先做一次模拟执行。
5. 确认持仓、订单和保护单都正常后，再手动启用策略。

## 代理说明

容器里的 `127.0.0.1` 指容器自身，不是 VPS 或你的电脑。若交易所需要代理，请填写容器可以访问的代理地址；不要关闭 TLS 证书校验。

## 更新项目

```sh
docker compose down
python3 scripts/backup.py --database data/trading.db --env .env
git pull
docker compose build
docker compose up -d
```

更新前先在页面暂停全部策略。不要同时启动旧服务和新容器。

## 迁移已有配置

1. 旧机器暂停策略，等待正在执行的任务结束，然后停止旧服务。
2. 在旧机器备份数据库和 `.env`：

   ```sh
   python3 scripts/backup.py
   ```

3. 把完整代码、备份数据库和备份 `.env` 传到新 VPS。
4. 保留原来的 `ENCRYPTION_KEY`，不要重新生成。
5. 恢复到新目录：

   ```sh
   python3 scripts/restore.py backups/备份目录 /新的恢复目录
   ```

6. 检查配置后再启动服务，并确认旧机器不会再次运行同一策略。

## 备份和恢复

备份包含数据库加密密钥，不能上传公开仓库：

```sh
python3 scripts/backup.py --database data/trading.db --env .env
python3 scripts/doctor.py --database data/trading.db --env .env
```

恢复前必须停止服务，目标目录必须是新目录：

```sh
python3 scripts/restore.py backups/备份目录 /新的恢复目录
```

恢复脚本会自动暂停策略，不会启动服务，也不会修改原备份。

## systemd 方案

适用于已安装 Python 3.12 的 Linux：

1. 创建专用用户 `jingxin`。
2. 把项目放到 `/opt/jingxin`，由该用户拥有。
3. 创建虚拟环境并安装 `requirements.txt`。
4. 运行 `python scripts/setup.py`。
5. 复制 `deploy/jingxin.service` 到 `/etc/systemd/system/`，再执行：

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now jingxin
   sudo systemctl status jingxin
   ```

Docker 和 systemd 只能选一个，不能同时启动。

## 当前限制

- 自动交易只支持 OKX 永续合约。
- 币安只支持凭据保存和只读连接测试。
- 现货未接入。
- 没有跨主机锁和完整订单幂等恢复，不适合多实例无人值守运行。
- 健康检查只代表 Web 服务能响应，不代表交易所、AI 或策略正常。
