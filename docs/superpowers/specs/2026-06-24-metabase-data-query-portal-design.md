# 数据查询门户（Metabase 只读 BI）— 设计

日期：2026-06-24
范围：新增一个**独立部署的数据查询门户**，供内部团队与少数科研同伴登录后查询 RDS 中的临床数据。
影响边界：**采集端 App（`蓝牙uniapp/`）零改动；现有后端（`back/` Flask）零改动**。新增物全部在 ECS / RDS / nginx / 部署文档层面。

## 背景与目标

采集已开始落库（`lanya` 库：clinicians / patients / patient_pii / devices / device_raw_data / device_transformed_data）。当前要查数据只能 SSH 上 ECS 敲 `mysql`，不方便，也无法安全地让同学自助查询。

目标：一个**公网可访问、需账号口令登录**的网站，登录后可以：
- 图形化（拖拽选条件出表格/图表，不写 SQL）查询采集数据；
- 管理员另有**只读 SQL 编辑器**做灵活查询；
- 一键导出 CSV。

并且必须守住医疗数据红线：**只读（不可改/删）**、**患者明文 PII 对外部人员不可见**、**RDS 不开公网**。

## 决策记录（已与用户确认）

| 议题 | 结论 |
|---|---|
| 使用对象 | A 内部团队（可看全部含 PII）+ B 少数同学/科研同伴（只读、看不到 PII） |
| 查询形态 | C 图形化查询 + 只读 SQL 编辑器（管理员与分析员都可用）；两者均只读 |
| 访问方式 | 公网子域 + HTTPS + 登录 |
| 选型 | 现成 BI：**Metabase**（开源），而非自研网页 SQL 控制台 |
| 运行方式 | ECS 上 **Docker** 容器运行 |
| ECS 规格 | 2 vCPU / 4 GiB（需限堆 + swap 兜底） |

选 Metabase 而非自研的核心理由：账号/角色/图形查询/只读 SQL 编辑器/CSV 导出/登录限流它**开箱即有**，省掉大量自研；而"自己做一个安全的网页 SQL 控制台"恰是最易出安全事故的部分，能不写就不写。

## 非目标（YAGNI）

- 不自研前端 UI、不自研登录鉴权、不自研 SQL 控制台（全部由 Metabase 提供）。
- 不改采集端 App、不改 `back/` Flask、不改 `lanya` 表结构。
- 不开 RDS 公网、不给同学开 ECS 数据库写权限。
- 暂不做"实验室只读副本/只读 API 导出"（架构方案阶段 3 的目标）；本门户是过渡期的安全自助查询入口，仍坚持只读 + PII 隔离。
- 不做邮件服务器对接（Metabase 邀请邮件可选；初期用管理员手动建账号设初始口令即可）。

## 架构

```
浏览器 ──HTTPS──> data.sarcopenianus.com  (nginx :443, 80→443 跳转)
                      │ 反向代理
                      ▼
                 Metabase 容器  (Docker, 仅监听 127.0.0.1:3000)
                      │ VPC 内网、只读账号
                      ▼
                 阿里云 RDS
                   ├── lanya     库（临床数据，被查询）
                   └── metabase  库（Metabase 自身配置/账号/图表，新建）
```

- Metabase 容器只绑定本机 `127.0.0.1:3000`，**不直接对公网**；对外一律经 nginx 加 HTTPS。
- RDS 维持私网；Metabase 经 VPC 内网地址连接，沿用现有 ECS→RDS 内网链路（已在白名单）。

## 数据库账号与 PII 隔离（双重锁，核心安全设计）

在 RDS 上新建 **1 个元数据库 + 3 个账号**：

| 账号 | 授权 | 用途 |
|---|---|---|
| （库）`metabase` | — | 新建空库，存 Metabase 自身配置 |
| `metabase_app` | `ALL PRIVILEGES ON metabase.*` | Metabase 应用账号，**只碰 metabase 库，不碰 lanya** |
| `mb_ro_full` | `SELECT ON lanya.*`（含 `patient_pii`） | 管理员组数据源 |
| `mb_ro_deid` | `SELECT` on `lanya` 的每张表**除 `patient_pii` 外** | 分析员组数据源 |

授权 SQL（由 RDS 高权限账号执行，口令占位、上线时换强口令）：

```sql
CREATE DATABASE IF NOT EXISTS metabase CHARACTER SET utf8mb4;

CREATE USER 'metabase_app'@'%' IDENTIFIED BY '<强口令1>';
GRANT ALL PRIVILEGES ON metabase.* TO 'metabase_app'@'%';

CREATE USER 'mb_ro_full'@'%' IDENTIFIED BY '<强口令2>';
GRANT SELECT ON lanya.* TO 'mb_ro_full'@'%';

CREATE USER 'mb_ro_deid'@'%' IDENTIFIED BY '<强口令3>';
-- 逐表授权，刻意跳过 patient_pii；新增表时需补授
GRANT SELECT ON lanya.clinicians              TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.patients                TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.devices                 TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.device_raw_data         TO 'mb_ro_deid'@'%';
GRANT SELECT ON lanya.device_transformed_data TO 'mb_ro_deid'@'%';
-- 注意：故意不授 lanya.patient_pii、不授 lanya.leads（留资信息也非分析所需）
FLUSH PRIVILEGES;
```

> 主机限定：`'%'` 为简化。RDS 白名单已只放行 ECS 内网，且 Metabase 只监听本机，风险可控；如需更严可把 `'%'` 收窄到 ECS 内网网段。

Metabase 内配置 **两个数据源 + 两个用户组**：

- 数据源「Lanya（含PII）」→ 连 `mb_ro_full`；数据源「Lanya（脱敏）」→ 连 `mb_ro_deid`。
- **管理员组**：可访问「含PII」数据源；开放原生 SQL 编辑器。
- **分析员组**：仅可访问「脱敏」数据源；**同样开放原生 SQL 编辑器**（应用户要求）。因其数据源连的是 `mb_ro_deid`，即便写 `SELECT * FROM patient_pii` 也会在数据库层被拒，PII 仍不可达。

**PII 隔离靠数据库授权这层兜底（最可靠的一层）**：分析员能写 SQL，但脱敏只读账号 `mb_ro_deid` 物理上 `SELECT` 不到 `patient_pii`，与 Metabase 的数据源/分组配置无关——配置即便误设也挡得住。**只读兜底**：所有账号均只读，任何人无法改/删临床数据（守住 raw append-only 红线）。

## 安全要点

- **传输**：全程 HTTPS，nginx 80→443 跳转。需为 `data.sarcopenianus.com` 配 DNS A 记录（→ `118.31.39.47`）+ 证书。现有阿里云免费 DV 证书只签了 `api.` 子域，需为 `data.` 子域加签 SAN 或单独签一张（同 3 个月续期节奏）。
- **口令/密钥**：3 个数据库账号口令、Metabase 管理员口令一律强口令；数据库口令存于 Metabase 配置（落在 `metabase` 库），**不进 git**。容器启动用的环境变量写在 ECS 上的 `docker run`/compose 文件或 systemd unit，含口令的文件 `chmod 600`、不入库。
- **入口加固**：依赖 Metabase 自带登录失败限流与会话管理；管理员强口令。
- **IP 白名单（后续启用）**：nginx 子域配置内预留 `allow/deny` 白名单块（初期注释/放开公网登录），待拿到你们固定出口 IP 后取消注释、收紧到白名单。
- **RDS**：维持不开公网；安全组 3306 仅对 ECS 内网。
- **审计**：Metabase 自带查询历史/登录日志，满足基本审计。

## 内存与运行

- 容器：`--memory=1.5g`，`JAVA_OPTS=-Xmx1g`（限 JVM 堆）。
- ECS 增加 **2–4 GB swap** 作安全垫，防与 gunicorn 同时尖峰 OOM。
- 预期常驻占用约 1.3 GB，叠加现有 nginx + gunicorn，在 4 GiB 上可行但偏紧，需观察。
- 数据持久化：Metabase 配置在 RDS `metabase` 库，容器本身无状态，升级=拉新镜像重建容器，配置不丢。

## 部署步骤（概要，细化到 plan）

1. ECS 安装 Docker。
2. 加 swap（2–4 GB）。
3. RDS 建 `metabase` 库 + 3 账号授权（上方 SQL）。
4. `docker run` 起 Metabase：环境变量 `MB_DB_TYPE=mysql`、`MB_DB_DBNAME=metabase`、`MB_DB_HOST=<RDS内网>`、`MB_DB_USER=metabase_app`、`MB_DB_PASS=...`，端口映射 `127.0.0.1:3000:3000`，加 `--memory`/`JAVA_OPTS`，`--restart=unless-stopped`。
5. nginx 新增 `data.sarcopenianus.com` server 块反代 `127.0.0.1:3000` + HTTPS；配置文件模板放 `deploy/`（如 `deploy/nginx-data.conf`）。
6. DNS A 记录 + 证书（加签/单签）。
7. Metabase 初始化向导：建管理员 → 加两个数据源 → 建两个用户组 → 配数据权限（分析员仅脱敏源、可用原生 SQL）→ 建/邀同学账号入分析员组。
8. 验收（见下）。

## 验收标准

- 管理员登录：能看到「含PII」数据源、能用 SQL 编辑器、能查到 `patient_pii` 字段、能导 CSV。
- 分析员登录：只看到「脱敏」数据源、**有只读 SQL 编辑器**，但对 `patient_pii` 的查询被数据库拒绝（写 `SELECT * FROM patient_pii` 报无权限）、能对 `device_raw_data` 等做图形化查询并导 CSV。
- 用脱敏账号直接对 `patient_pii` 发 `SELECT` → 数据库层报无权限（双重锁验证）。
- 任一账号尝试 `UPDATE/DELETE/INSERT` → 失败（只读验证）。
- 公网 `https://data.sarcopenianus.com` 证书可信、HTTP 自动跳 HTTPS；RDS 仍无公网。
- ECS 内存在 Metabase + gunicorn 同时运行下稳定（观察一段时间无 OOM）。

## 交付物清单

- ECS：Docker + Metabase 容器（systemd 或 compose 托管）+ swap。
- RDS：`metabase` 库 + 3 个账号。
- 仓库：`deploy/nginx-data.conf`（nginx 子域模板）+ 一份部署/账号授权文档（口令用占位，真实口令不入库）。
- Metabase 内：两数据源 / 两用户组 / 权限配置 / 初始账号。
- CLAUDE.md、系统架构方案.md 同步记录本门户。
