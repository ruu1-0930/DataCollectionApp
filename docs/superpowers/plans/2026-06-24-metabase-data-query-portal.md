# 数据查询门户（Metabase 只读 BI）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ECS 上用 Docker 部署一个只读 Metabase 门户，公网子域 + HTTPS + 登录，让内部团队（含 PII）与同学（脱敏）安全自助查询 RDS 临床数据。

**Architecture:** 浏览器 → nginx(443, `data.sarcopenianus.com`) → Metabase 容器(127.0.0.1:3000) → RDS（`lanya` 只读、`metabase` 元数据库）。PII 隔离靠数据库授权层（脱敏只读账号 `mb_ro_deid` 物理上读不到 `patient_pii`）；所有数据库账号只读，杜绝改/删。

**Tech Stack:** Docker + Metabase（开源镜像）、MySQL（阿里云 RDS）、nginx 反代 + 阿里云 DV 证书。

参考 spec：`docs/superpowers/specs/2026-06-24-metabase-data-query-portal-design.md`

---

## 文件结构（仓库内新增/修改）

仓库内只产出"部署资产 + 文档"，没有应用代码（Metabase 是现成镜像）：

- 新建 `deploy/nginx-data.conf` — 子域反代 + HTTPS + 预留 IP 白名单块。
- 新建 `deploy/metabase/docker-compose.yml` — Metabase 容器定义（限内存、绑本机、元数据指向 RDS）。
- 新建 `deploy/metabase/.env.example` — 容器环境变量模板（RDS 地址 + Metabase 应用库口令，占位，真实值不入 git）。
- 新建 `deploy/metabase/README.md` — 服务器端部署运行手册（含 RDS 建库授权 SQL、Docker/swap/证书/向导/验收）。
- 修改 `CLAUDE.md`、`系统架构方案.md` — 记录本门户。

> 真实口令只写在 ECS 上的 `deploy/metabase/.env`（不提交）；`.env.example` 用占位值入库。

---

## Part A：仓库内部署资产（本地创建 + 提交）

### Task 1：nginx 子域反代配置

**Files:**
- Create: `deploy/nginx-data.conf`

- [ ] **Step 1：创建 `deploy/nginx-data.conf`，内容如下**

```nginx
# 数据查询门户（Metabase）nginx 反向代理配置
# 放到 /etc/nginx/sites-available/data，软链到 sites-enabled 启用。
# 域名 data.sarcopenianus.com，阿里云免费 DV 证书（DigiCert，3 个月，到期前重签替换）。
# 前提：① 子域已解析(A→118.31.39.47)、备案覆盖根域；② 安全组放行 443；
#       ③ 证书已上传 /etc/nginx/ssl/；④ Metabase 容器监听 127.0.0.1:3000。

server {
    listen 80;
    server_name data.sarcopenianus.com;
    return 301 https://$host$request_uri;   # http 全部跳 https
}

server {
    listen 443 ssl;
    server_name data.sarcopenianus.com;

    ssl_certificate     /etc/nginx/ssl/data.sarcopenianus.com.pem;
    ssl_certificate_key /etc/nginx/ssl/data.sarcopenianus.com.key;   # chmod 600，勿入 git
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ── IP 白名单（后续启用）──────────────────────────────
    # 拿到固定出口 IP 后取消注释，把 x.x.x.x 换成实际 IP，deny all 兜底。
    # allow 1.2.3.4;
    # allow 5.6.7.8;
    # deny all;
    # ────────────────────────────────────────────────────

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;   # 大查询可能较久，避免 504
    }
}
```

- [ ] **Step 2：提交**

```bash
git add deploy/nginx-data.conf
git commit -m "deploy: nginx 子域反代 Metabase 门户(data.sarcopenianus.com) + 预留 IP 白名单"
```

---

### Task 2：Metabase 容器定义与环境变量模板

**Files:**
- Create: `deploy/metabase/docker-compose.yml`
- Create: `deploy/metabase/.env.example`

- [ ] **Step 1：创建 `deploy/metabase/docker-compose.yml`**

```yaml
# Metabase 只读 BI 门户。元数据存 RDS 的 metabase 库（无状态容器，升级=换镜像）。
# 只绑 127.0.0.1:3000，对外由 nginx(deploy/nginx-data.conf) 加 HTTPS。
# 4GiB ECS：限堆 1g + 容器内存 1536m；另需 ECS 上 2-4G swap（见 README）。
services:
  metabase:
    image: metabase/metabase:latest   # 建议改为 hub 上当前稳定 tag 固定版本
    container_name: metabase
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    env_file:
      - .env
    environment:
      MB_DB_TYPE: mysql
      MB_DB_DBNAME: metabase
      MB_DB_PORT: "3306"
      MB_DB_HOST: ${RDS_HOST}
      MB_DB_USER: metabase_app
      MB_DB_PASS: ${MB_APP_DB_PASS}
      JAVA_TIMEZONE: Asia/Shanghai
      JAVA_OPTS: "-Xmx1g"
    mem_limit: 1536m
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
```

- [ ] **Step 2：创建 `deploy/metabase/.env.example`**

```bash
# 复制为 deploy/metabase/.env 并填真实值；.env 含口令，禁止提交 git。
# RDS 内网地址（与 back/.env 的 DB_HOST 相同）
RDS_HOST=rm-xxxxxx.mysql.rds.aliyuncs.com
# Metabase 应用账号 metabase_app 的口令（仅对 metabase 库有权，见 README 授权 SQL）
MB_APP_DB_PASS=replace_with_strong_password
```

- [ ] **Step 3：确认 `.env` 已被 git 忽略**

Run: `git check-ignore deploy/metabase/.env || echo "NOT IGNORED — 需补 .gitignore"`
Expected: 打印路径（已忽略）。若打印 "NOT IGNORED"，在仓库根 `.gitignore` 追加一行 `deploy/metabase/.env` 后再继续。

- [ ] **Step 4：提交**

```bash
git add deploy/metabase/docker-compose.yml deploy/metabase/.env.example
git commit -m "deploy: Metabase docker-compose + 环境变量模板(限堆/限内存/元数据指向RDS)"
```

---

### Task 3：服务器端部署运行手册

**Files:**
- Create: `deploy/metabase/README.md`

- [ ] **Step 1：创建 `deploy/metabase/README.md`，内容如下**

````markdown
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
````

- [ ] **Step 2：提交**

```bash
git add deploy/metabase/README.md
git commit -m "deploy: Metabase 门户服务器端部署运行手册(RDS授权/swap/Docker/证书/向导/验收)"
```

---

### Task 4：文档同步（CLAUDE.md + 系统架构方案.md）

**Files:**
- Modify: `CLAUDE.md`
- Modify: `系统架构方案.md`

- [ ] **Step 1：在 `CLAUDE.md` 第 5 节"关键代码索引"补一条**

在该节末尾追加：

```markdown
- 数据查询门户（Metabase 只读 BI，公网 `https://data.sarcopenianus.com`）：部署资产 `deploy/nginx-data.conf`、`deploy/metabase/{docker-compose.yml,.env.example,README.md}`；设计/计划 `docs/superpowers/{specs,plans}/2026-06-24-metabase-data-query-portal*.md`。两个只读数据库账号 `mb_ro_full`(含PII)/`mb_ro_deid`(脱敏)，元数据库 `metabase`。采集端 App 与 back/ 零改动。
```

- [ ] **Step 2：在 `系统架构方案.md` 阶段 3（实验室分析侧）相关位置补一段**

记录：当前已落地一个**过渡期只读查询门户**（Metabase），供内部 + 同学自助查询；坚持只读 + PII 数据库层隔离；与阶段 3 最终的"只读 API/只读副本 + 去标识化导出"并行，后续可迁移收敛。

- [ ] **Step 3：提交**

```bash
git add CLAUDE.md 系统架构方案.md
git commit -m "docs: 记录 Metabase 数据查询门户(部署资产+只读账号+边界)"
```

---

## Part B：服务器端部署（在 ECS/RDS/阿里云控制台执行）

> Part B 不产生仓库改动，全部按 `deploy/metabase/README.md` 执行；下面把它拆成可勾选任务，每步带验证与预期输出。需要 SSH 到 `118.31.39.47` 与 RDS 高权限账号。

### Task 5：RDS 建库与授权
- [ ] 执行 README §1 的授权 SQL（三个强口令记到密码管理器，`metabase_app` 的口令稍后填进 `.env`）。
- [ ] 验证：
  - Run: `mysql -h "$RDS_HOST" -u mb_ro_deid -p -e "SHOW GRANTS;"`
  - Expected: 列出对 `lanya` 各表的 `SELECT`，**不含 `patient_pii`**。

### Task 6：ECS 加 swap
- [ ] 执行 README §2。
- [ ] 验证：`free -h` → Swap 行显示 4.0Gi。

### Task 7：装 Docker
- [ ] 执行 README §3。
- [ ] 验证：`docker compose version` 打印版本号；`sudo systemctl is-active docker` → `active`。

### Task 8：起 Metabase 容器
- [ ] 拷贝 `deploy/metabase/` 到 `/opt/lanya/metabase/`，`cp .env.example .env` 并填 `RDS_HOST`、`MB_APP_DB_PASS`（=强口令1）。
- [ ] 执行 README §4 `docker compose up -d`。
- [ ] 验证：`curl -s http://127.0.0.1:3000/api/health` → `{"status":"ok"}`（首启等 1-2 分钟）；`docker stats --no-stream metabase` 内存 < 1.5G。

### Task 9：DNS + 证书 + nginx 子域
- [ ] 执行 README §5（DNS A 记录、证书上传、`chmod 600` 私钥）。
- [ ] 执行 README §6 启用 nginx。
- [ ] 验证：`sudo nginx -t` → ok；外部浏览器访问 `https://data.sarcopenianus.com` 证书可信、出现 Metabase 登录/初始化页。

### Task 10：Metabase 向导 + 角色配置
- [ ] 执行 README §7（管理员、两数据源、两组、权限、同学账号）。
- [ ] 验证：执行 README §8 全部验收点通过（脱敏账号读 PII 被拒、写被拒；全量账号读 PII 成功；两类账号浏览器行为符合预期）。

---

## Self-Review（已对照 spec 自检）

- **Spec 覆盖**：架构(Task 1/2/8/9)、双重锁账号(Task 5 + README §1)、PII 隔离验收(Task 10/§8)、HTTPS 子域(Task 1/9)、内存调优+swap(Task 2/6)、分析员开只读 SQL(README §7.5)、IP 白名单预留(Task 1)、交付物与文档(Task 3/4)——逐项有任务对应。
- **占位符**：仅 `.env`/SQL 口令为有意占位（密钥不入库），镜像 tag 用真实 `latest` 并注明可固定版本；无 TODO/TBD。
- **一致性**：账号名 `metabase_app`/`mb_ro_full`/`mb_ro_deid`、库名 `metabase`/`lanya`、域名 `data.sarcopenianus.com`、端口 `127.0.0.1:3000` 在 spec/compose/nginx/README 全程一致。
