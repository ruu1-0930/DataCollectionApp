# Metabase 数据查询门户 — 部署运行手册

只读 BI 门户，公网 `https://data.sarcopenianus.com`。本文件是服务器端（ECS/RDS/阿里云控制台）操作步骤；仓库内只有 `docker-compose.yml` / `nginx-data.conf` / 本文件。

## 0. 前提
- ECS：`118.31.39.47`，2vCPU/4GiB，已跑 nginx + gunicorn。
- RDS：内网地址同 `back/.env` 的 `DB_HOST`，含 `lanya` 库。
- 已有阿里云账号可申请 DV 证书、改 DNS。

## 1. RDS：建元数据库 + 3 个只读/受限账号
用 RDS 高权限账号执行（口令换成强口令，三个各不相同）：

```sql
CREATE DATABASE IF NOT EXISTS metabase CHARACTER SET utf8mb4;

-- Metabase 应用账号：只碰 metabase 库
CREATE USER 'metabase_app'@'%' IDENTIFIED BY '<强口令1>';
GRANT ALL PRIVILEGES ON metabase.* TO 'metabase_app'@'%';

-- 管理员组数据源：lanya 全表只读（含 patient_pii）
CREATE USER 'mb_ro_full'@'%' IDENTIFIED BY '<强口令2>';
GRANT SELECT ON lanya.* TO 'mb_ro_full'@'%';

-- 分析员组数据源：lanya 除 patient_pii 外只读（逐表授权，刻意跳过 PII）
CREATE USER 'mb_ro_deid'@'%' IDENTIFIED BY '<强口令3>';
GRANT SELECT ON lanya.clinicians              TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.patients                TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.devices                 TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.device_raw_data         TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.device_transformed_data TO 'mb_ro_deid'@'%';
-- 不授 lanya.patient_pii、不授 lanya.leads
FLUSH PRIVILEGES;
```

> 新增 `lanya` 表时，记得给 `mb_ro_deid` 补 `SELECT`（除非该表含 PII）。

## 2. ECS：加 swap（4GiB 偏紧，必做）
```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # 预期 Swap 行显示 4.0Gi
```

## 3. ECS：安装 Docker（阿里云镜像源，国内可达）
官方 `get.docker.com` 在国内常连 `download.docker.com` 被重置，改用阿里云源装 `docker-ce` + compose 插件（Ubuntu 22.04 实测可用）：
```bash
# 清掉官方脚本可能写坏的残留源（没有也无妨）
sudo rm -f /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc
# 基础依赖
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
# 阿里云 docker GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
# 加阿里云 docker-ce 源
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
# 安装并启动
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
docker compose version   # 预期打印 Docker Compose version v2.x
```

镜像加速器（拉 Docker Hub 镜像同样会卡，**必配**，否则后面拉 metabase 镜像会超时）：
```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{ "registry-mirrors": ["https://docker.m.daocloud.io", "https://dockerproxy.com"] }
EOF
sudo systemctl restart docker
docker info | grep -A2 'Registry Mirrors'   # 确认已加载
sudo docker run --rm hello-world             # 预期 Hello from Docker!
```
> 更稳：阿里云控制台 → 容器镜像服务 ACR → 镜像加速器，用账号**专属** `https://xxxx.mirror.aliyuncs.com` 替换上面列表里的公共镜像。

## 4. ECS：取部署文件 + 起 Metabase 容器
ECS 上已有仓库 `/opt/DataCollectionApp`。只检出 metabase 部署文件（**不切分支、不影响正在跑的后端**）：
```bash
cd /opt/DataCollectionApp
git fetch origin
git checkout origin/feature/frontend-backend-alignment -- deploy/metabase deploy/nginx-data.conf
ls deploy/metabase   # 预期：docker-compose.yml  .env.example  README.md
```
直接在仓库目录起容器（无需另拷到 /opt/lanya）：
```bash
cd /opt/DataCollectionApp/deploy/metabase
cp .env.example .env && vi .env     # 填 RDS_HOST 与 MB_APP_DB_PASS(=授权SQL里 metabase_app 的口令)
sudo docker compose up -d
sudo docker ps                       # 预期 metabase 容器 Up
curl -s http://127.0.0.1:3000/api/health   # 预期 {"status":"ok"}（首启迁移需 1-2 分钟）
```

## 5. 阿里云：DNS + 证书
- DNS：加 A 记录 `data` → `118.31.39.47`。
- 证书：申请 `data.sarcopenianus.com` 的免费 DV 证书（或给现有证书加该 SAN），下载 nginx 格式，上传到 ECS：
  - `/etc/nginx/ssl/data.sarcopenianus.com.pem`
  - `/etc/nginx/ssl/data.sarcopenianus.com.key`（`sudo chmod 600`）
- 安全组确认放行 443。

## 6. ECS：启用 nginx 子域
```bash
sudo cp /opt/DataCollectionApp/deploy/nginx-data.conf /etc/nginx/sites-available/data
sudo ln -s /etc/nginx/sites-available/data /etc/nginx/sites-enabled/data
sudo nginx -t            # 预期 syntax is ok / test is successful
sudo systemctl reload nginx
curl -I https://data.sarcopenianus.com   # 预期 200 或 302（跳 /setup）
```

## 7. Metabase 向导（浏览器打开 https://data.sarcopenianus.com）
1. 建管理员账号（强口令）。
2. 跳过/稍后再连数据源（向导里先连一个也行）。
3. Admin → Databases，**加两个数据源**（都 MySQL、host=RDS 内网、db=lanya）：
   - 「Lanya（含PII）」用 `mb_ro_full`。
   - 「Lanya（脱敏）」用 `mb_ro_deid`。
4. Admin → People → Groups，建两组：`管理员`、`分析员`。
5. Admin → Permissions → Data：
   - `管理员` 组：对「Lanya（含PII）」与「Lanya（脱敏）」可查 + 允许 Native query。
   - `分析员` 组：仅对「Lanya（脱敏）」可查 + **允许 Native query**（应用户要求）；对「Lanya（含PII）」设为 No self-service / Blocked。
6. People → 新建/邀请同学账号，加入 `分析员` 组；你自己/内部加入 `管理员` 组。

## 8. 验收（在 ECS 上跑 mysql 校验双重锁；浏览器校验角色）
```bash
# 脱敏账号读 PII —— 必须被数据库拒
mysql -h "$RDS_HOST" -u mb_ro_deid -p lanya -e "SELECT * FROM patient_pii LIMIT 1;"
# 预期: ERROR 1142 ... SELECT command denied ... table 'patient_pii'

# 脱敏账号写 —— 必须被拒（只读）
mysql -h "$RDS_HOST" -u mb_ro_deid -p lanya -e "DELETE FROM device_raw_data LIMIT 1;"
# 预期: ERROR 1142 ... DELETE command denied

# 全量只读账号读 PII —— 应成功
mysql -h "$RDS_HOST" -u mb_ro_full -p lanya -e "SELECT COUNT(*) FROM patient_pii;"
# 预期: 返回一个计数
```
浏览器：用分析员账号登录 → 只见「脱敏」源、有 SQL 编辑器但 `SELECT * FROM patient_pii` 报无权限、能图形化查 `device_raw_data` 并导 CSV；用管理员账号登录 → 能见「含PII」源、能查到 PII 字段。

## 常见问题（首次部署实测踩过的坑）
1. **加 Docker 后 `mysql` 连 RDS 报 `(113) No route to host`**：Docker 默认网桥 `docker0=172.17.0.0/16` 跟 RDS 内网 IP（如 `172.17.x.x`）撞了，路由被网桥劫走。修：在 `/etc/docker/daemon.json` 把网桥和地址池挪到 `10.x` 段——
   ```json
   { "registry-mirrors": ["..."], "bip": "10.222.0.1/24", "default-address-pools": [{ "base": "10.223.0.0/16", "size": 24 }] }
   ```
   `sudo systemctl restart docker` 后 `ip -br addr show docker0` 应变 `10.222.x`。已建的旧网络要 `docker compose down && docker network rm metabase_default` 再 `up` 才会用新网段。
2. **容器日志 `Unable to connect to Metabase mysql DB` / c3p0 `checkout timed out`**：多半不是网络，是 **`.env` 的 `MB_APP_DB_PASS` 和 RDS 里 `metabase_app` 的真实口令不一致**（认证失败被连接池包装成超时）。用 `ALTER USER 'metabase_app'@'%' IDENTIFIED BY '...'` 把两边对齐。验证：`sudo docker run --rm --network metabase_default mysql:8 mysql -h<RDS> -umetabase_app -p<口令> metabase -e "SELECT 1;"`。
3. **迁移卡 `v49.00-059` 报 `Invalid default value for 'updated_at'`**：RDS `sql_mode` 含 `NO_ZERO_DATE,NO_ZERO_IN_DATE`，Metabase 统一时间列类型时被拒。修：阿里云 RDS 控制台 → 参数设置 → `sql_mode` 去掉这两项（动态生效，无需重启实例；保留 `STRICT_TRANS_TABLES`/`ONLY_FULL_GROUP_BY`，对 `lanya` 只放宽不收紧）。改完 `DROP DATABASE metabase; CREATE DATABASE metabase CHARACTER SET utf8mb4;` 清掉半成品表，再 `docker compose down && up`。

## 维护
- 升级：`cd /opt/DataCollectionApp/deploy/metabase && sudo docker compose pull && sudo docker compose up -d`（配置在 RDS 不丢）。
- 证书：同 api 那张，3 个月到期前重签替换 `/etc/nginx/ssl/data.*` 并 `nginx -t && systemctl reload nginx`。
- 内存：`free -h`、`docker stats metabase` 观察；如吃紧把 `JAVA_OPTS` 降到 `-Xmx768m`。
