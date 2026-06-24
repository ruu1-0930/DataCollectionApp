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

## 3. ECS：安装 Docker（含 compose 插件，发行版无关）
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
docker compose version   # 预期打印版本号
```

## 4. ECS：起 Metabase 容器
```bash
sudo mkdir -p /opt/lanya/metabase
# 把仓库 deploy/metabase/{docker-compose.yml,.env.example} 拷到此目录
cd /opt/lanya/metabase
cp .env.example .env && vi .env     # 填 RDS_HOST 与 MB_APP_DB_PASS(=授权SQL里的强口令1)
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
sudo cp nginx-data.conf /etc/nginx/sites-available/data
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

## 维护
- 升级：`cd /opt/lanya/metabase && sudo docker compose pull && sudo docker compose up -d`（配置在 RDS 不丢）。
- 证书：同 api 那张，3 个月到期前重签替换 `/etc/nginx/ssl/data.*` 并 `nginx -t && systemctl reload nginx`。
- 内存：`free -h`、`docker stats metabase` 观察；如吃紧把 `JAVA_OPTS` 降到 `-Xmx768m`。
