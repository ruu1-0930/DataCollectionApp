# CLAUDE.md

本文件为本仓库后续开发的基本约束与导航。**开始任何开发前，请先阅读架构方案。**

> 📐 **架构与改造方案（必读）**：[系统架构方案.md](系统架构方案.md)
> 其中包含现状梳理、差距分析、目标架构、分阶段改造路线图（阶段 0–5）、数据模型扩展、技术选型与 FAQ。

---

## 1. 项目概览

这是一套 **"蓝牙鞋垫数据采集 + 云端分析"** 的端到云系统（**不是单纯的 App**），目标是支撑
**"设备在医院采集 → 数据上传云端 → 研发/科研团队在实验室分析"**。

代码基线：`DataCollectionApp/`

| 模块 | 路径 | 技术栈 | 职责 |
|---|---|---|---|
| 采集端 App | `蓝牙uniapp/` | uni-app + Vue3 + Pinia + UTS 原生蓝牙 | 连鞋垫、解析传感器、上传、设备管理 |
| 云后端 | `back/` | Flask + SQLAlchemy + PyJWT | 鉴权、设备/数据接口、SVM 推理 |
| 数据库 | （远程 MySQL） | MySQL 5.7+ | 用户/设备/原始数据/分析数据/周计划 |
| 管理台 | `admin/` | Vue3 + Vite + UnoCSS | 管理员后台 |

环境要求：Python 3.7+、Node.js 14+、MySQL 5.7+。

---

## 2. 当前优先级（按架构方案的阶段推进）

0. **🔴 进行中 — 迁移到自有云**：现有 ECS/数据库**均不在我方名下**（随时可能停机），迁到自有阿里云 **ECS + RDS**（同 VPC、RDS 不开公网）。**当前任务，先于阶段 1。** 因**尚未开始采集，无历史数据需迁移**，成本最低；迁移顺带完成阶段 1 的 HTTPS、收回 DB 公网、密钥/口令入环境变量（最后一项已完成）。逐步操作见 [迁移操作清单.md](迁移操作清单.md)；背景见架构方案阶段 0.5 与 FAQ 10.2。
   - **已完成**：ECS+RDS 开通、建库导 schema、gunicorn+systemd+nginx 部署跑通（公网 IP `118.31.39.47`）；三端地址改到新服务器；清理上一个开发者「捡漏/短剧」模板残留。
   - ✅ **域名 + HTTPS 已上线（2026-06-15）**：域名 `api.sarcopenianus.com`（备案通过，A 记录 → `118.31.39.47`），阿里云免费 DV 证书（DigiCert，有效期 **2026-06-15→09-12，3 个月，到期前需重签替换**）。nginx 切 443（80→443 跳转），证书在 ECS `/etc/nginx/ssl/`（私钥 chmod 600，**不入 git**），安全组放行 443。公网 `https://api.sarcopenianus.com` 证书可信、链路 `nginx(443)→gunicorn(5000)→Flask` 验证通过。三端地址全部切到 https：`蓝牙uniapp/config/index.js`、`utils/request.js`(`sslVerify:true`)、`admin/.env`(4 处)、`admin/vite.config.js`(代理 target)、`admin/src/config/index.js`。配置模板见 `deploy/nginx-lanya.conf`。
   - **待办**：**HBuilderX 重打包 App**（https 地址打进 apk 才生效）+ 重新部署 admin；关 RDS 公网、复查安全组（5000 不对公网/22 仅对己）、下线旧机器；证书到期前续签。
1. **🟠 阶段 1 — 止血（部分完成）**：
   - ✅ **后端净重设（scope A，已完成）**：六表临床模型（clinicians/devices/patients/patient_pii/device_raw_data/device_transformed_data）+ 医护口令认证（bcrypt + JWT）+ 采集归属 clinician+patient+device + 按患者历史只读 API。子 agent 驱动 TDD，34 测试全绿。见 `back/` 与 `database_schema_mysql.sql`。
   - ✅ **App 端接入新接口（代码完成，scope A）**：分支 `feature/frontend-backend-alignment`，子 agent 驱动 12 任务。`utils/terminal.js`（terminal_code）、`api/{clinician,patient,device}.js` 薄封装、`utils/apiShape.js`（后端↔前端形状映射）、`request.js`（token 走 `auth.getToken()`「Bearer xxx」整串 + 401 静默重登）、`operatorStore.enable/refreshToken`（启用即 enable→发 token）、`patientStore` 改后端发 `id/subject_id`、患者新建/选择页接 `POST/GET /patients`、采集上传补 `patient_id` 且无当前患者禁采、数据页按 `/patients/<id>/data` 拉历史、删除作废 `api/user.js` 与旧登录 `store/modules/user.js`。纯函数 vitest 22 测试全绿。对齐 spec/plan 见 `docs/superpowers/{specs,plans}/2026-06-07-frontend-backend-alignment.md`。
   - ✅ **6→38 维全量落库（每脚一行，代码完成）**：一帧 BLE = 合并 38 字段（**固定前 19 左脚 / 后 19 右脚**），后端摄取拆成 L/R 两条每脚记录入库。`device_raw_data` 由「6 轴 IMU」扩为每脚 `foot`(L/R)+9 压力 `p1..p9`+6 IMU+4 步态（步长/步速/单支撑/双支撑，皆为设备固件输出，非本仓库模型计算；仅 SVM T1–T5 为推理）。改动文件：`models/models.py`、`database_schema_mysql.sql`、`migrations/001_raw_data_per_foot.sql`、`api/device.py`(38→2 行拆分 + 每脚跑 SVM)、`api/patient.py`(历史返回带 `foot`+全量压力/步态)；App `utils/apiShape.js` 的 `mapHistoryItem` 同步暴露 `foot`/`pressure`/步态。**后端 35 测试 + App 22 vitest 全绿**。`蓝牙uniapp` 上传侧无需改（已发 38 命名字段，拆分在后端）。
   - 🟡 **App 端真机回归（部分已验，2026-06-09）**：HBuilderX → 真后端 `http://118.31.39.47`。
     - ✅ **已真机验证**：启用本机（注册医护）、选/建患者——数据已确认落 RDS（`clinicians`/`patients`/`patient_pii` 可查到，归属链 `clinician_id` 一致）；新增设备已由**扫码改为蓝牙搜索附近设备**（修复了运行时权限未申请导致扫不到的问题，见 `store/modules/blueTooth.js` 的 `requestBlePermissions`/`syncBluetoothState`）。
     - ⏳ **待验**：连接鞋垫 → 采集 → 上传落库 + 归属（查 `device_raw_data` 每帧 L/R 两行 + `device_transformed_data` T1-T5 + `patients.last_collected_at`）、按患者查历史（数据页）。store/页面/蓝牙/网络无法 vitest mock，见 plan Task 12 手动清单。
     - HTTPS/密钥/收回公网随迁移完成。
2. 🟠 阶段 2 — 可靠采集（批量上传 + 离线重传）
3. 🟠 阶段 3 — 实验室分析侧（科研只读 API + 去标识化导出）
4. 🟡 阶段 4 — 采集与分析解耦（SVM 异步化）
5. 阶段 5 — 规模化与运维

改动前请对照 [系统架构方案.md](系统架构方案.md) 第 5 节确认当前阶段与验收标准。

### 2.1 并行线 — 采集端 App 前端改版（UI 重构）

与云迁移并行的一条 UI 线，**目标：界面更专业 + 把「个人 App」模型改成「医护操作员 + 患者档案」临床多患者模型**。

- **状态**：✅ 设计与实现计划已定稿；✅ git 仓库就绪（仓库根 = `DataCollectionApp/`）；✅ **15 任务全部实现完成**（分支 `feature/frontend-redesign`，子 agent 驱动开发 + 逐任务评审）。
  - 设计 spec：[docs/superpowers/specs/2026-06-06-frontend-redesign-design.md](docs/superpowers/specs/2026-06-06-frontend-redesign-design.md)
  - 实现计划（15 任务 / 3 阶段）：[docs/superpowers/plans/2026-06-06-frontend-redesign.md](docs/superpowers/plans/2026-06-06-frontend-redesign.md)
  - **已交付**：SCSS 设计令牌（`styles/tokens.scss` + `uni.scss`）；纯逻辑 `utils/patient.js` + vitest（12 测试全过）；本地存储 `utils/clinicStorage.js`；`operatorStore`/`patientStore`；基础组件 `components/base/Ca*.vue`（CaInput/CaCard/CaEmpty/CaMetric/CaStatusStrip/CaPatientBar）；启动网关（`App.vue` onLaunch）+ 路由（`pages.json`）；启用/解锁页（`pages/setup/*`）、患者选择/新建页（`pages/patient/*`）；首页实时区改版（**足底压力图保持原实现不变**）；数据分析页重做；我的页改造为「操作员资料 + 设备管理」（移除 App 登录态与采样频率/开关控制）。
  - **顺带清理**：删除 `login`/`register`/`profile` 及 `*copy.vue` 死文件；`request.js`/`user.js` 解除旧登录模型副作用（无 token 请求静默取消，不再 `uni.clearStorage()`/跳登录页，避免误删本地临床数据）。
  - **仍待办（真机验证）**：HBuilderX 真机跑全流程回归（蓝牙连接/采集态需真机；「新增设备」已由扫码改蓝牙搜索附近设备），见计划 Task 15 手动清单；遗留 `pages/index/index` 蓝牙测试页未删（已派后续任务）。
  - **🆕 首页足底压力热力图 + IMU 实时显示（代码完成，2026-06-10）**：把每帧 38 字段里此前没可视化的 9 路压力与 6 轴 IMU 画到首页。足图 9 个点位按硬件 schema `p1..p9` 重排（下标=传感器号），按 ADC 压力着色（**固定满量程 `PMAX=4093`**，浅蓝→深蓝，跨帧/跨脚绝对可比）并把整数 ADC 值叠在点上；新增可折叠「IMU 原始数据」卡（左右脚各 加速度/角速度 6 轴，2 位小数）；实时参数里步长由设备发的米改为 **×100 显示 cm**。着色/换算抽成纯函数 `utils/footMetrics.js`（`shade`/`mToCm`/`PMAX`）+ vitest（8 用例，全套 30 全绿）；store `realtime` 扩出每脚 `pressure[9]`+`imu`（`emptyRealtime()` 工厂统一复位）。改动文件：`store/modules/blueTooth.js`、`pages/home/home.vue`、`utils/footMetrics.js`（新）。**后端零改动**（38 字段早已落库，本次只是把已有字段画出来）。spec/plan：`docs/superpowers/{specs,plans}/2026-06-10-home-pressure-heatmap-imu*.md`。**待真机验证**：连接采集时足图随按压变色显数、IMU 卡展开见 6 轴、步长 cm/步速 m/s、断开归零走空态。
- **核心模型变更**：取消 App 账号登录；改为**设备级一次性启用（医院/科室/医生/联系方式 + 自设口令）→ 解锁 → 选/建患者 → 当前患者上下文**。采集数据带「医院/科室/医生 + 患者编号」；患者无账号、无密码，系统自动派假名 `subject_id`（如 `#00427`），导出只用编号。
- **明确保留**：首页足底压力图底图沿用原实现（`foot.png`）。注：2026-06-10 把原静态蓝点 ripple 升级为压力热力图 + 数字（见上方「已交付」🆕 条），点位坐标不变、底图不变。
- **范围边界**：本线只做**视觉 + 交互流程**（用示意数据/空态）。**真实数据接入 + 后端模型改造**（操作员/患者表、`subject_id`、PII 与传感器分表、采集归属、按患者历史只读 API、去标识化导出）划为**后续计划**，与阶段 1/3 合并实现。
- **后端依赖提醒**：现后端 user 表/登录模型与新「操作员+患者」模型不匹配，前端先行、接口未就绪处走空态；落地真实数据时需同步改 `back/` 与 `database_schema_mysql.sql`。

---

## 3. 开发约束（硬性）

### 3.1 数据完整性
- 鞋垫上传的 **38 个字段必须全量落库**，禁止再丢弃压力/右脚/步态数据。字段顺序/含义以硬件文档为准，**改解析逻辑前先与硬件团队核对**（现状靠 CSV split 顺序硬编码，见 `蓝牙uniapp/store/modules/blueTooth.js:187`）。
- **原始数据（raw）只增不改**（append-only）；分析结果单独存，可重算。

### 3.2 安全与隐私（医疗数据红线，不可妥协）
- **禁止明文传输**：一律 HTTPS；App 端不得保留 `sslVerify:false`。
- **禁止硬编码密钥/口令**：数据库口令、`SECRET_KEY` 等一律走环境变量，不进代码、不进 git。
- **禁止数据库公网裸奔**：3306 只对后端内网开放。
- **登录必须校验密码/验证码**，不得仅凭姓名/手机号签发 Token。（前端改版后 App 侧改为设备级口令门禁 + 患者 `subject_id`，见 2.1；后端真实接入时仍须有真正的鉴权，不得无密码签发 Token。）
- **患者 PII（姓名/手机/邮箱/住址）**：与传感器数据分离；对外导出默认去标识化（用假名 `subject_id`）。
- **实验室不直连生产库**：通过只读 API 或只读副本取数。
- 提交前自查：不要把 `.env`、含真实口令的 `config.py`、密钥文件加入提交。

### 3.3 工程规范
- **迁移服务器须同步三处**：`back/config.py`（DB 串）、`蓝牙uniapp/config/index.js`（`baseURL`）、并**重新打包 App**（地址打包进 apk）。详见架构方案 FAQ 10.2。
- 生产部署后端用 **gunicorn + nginx**，不要用 `app.run`。
- 改 DB 表结构走 **`ALTER` + 测试库演练 + 数据迁移**，不直接动生产；schema 变更同步更新 `back/database_schema_mysql.sql`。
- 上传链路保持轻量：**摄取只负责可靠落库，推理/分析异步化**，不要在请求内做重计算。
- 注释只解释"为什么"，不堆砌"做了什么"；不引入超出当前任务需要的抽象。
- 每次执行完任务之后，同步更新维护CLAUDE.md以及系统架构方案.md，已记录最新进展和已完成工作。

---

## 4. 本地运行

**后端**
```bash
cd back
python -m venv venv && .\venv\Scripts\activate   # Windows
pip install -r requirements.txt
# 修改 config.py 中数据库连接信息后
python app.py        # 默认 http://0.0.0.0:5000
```

**采集端 App（uni-app）**
```bash
cd 蓝牙uniapp
# 用 HBuilderX 打开，运行到 Android 真机（蓝牙原生模块需真机/自定义基座）
# 修改 config/index.js 的 baseURL 指向你的后端
```

**管理台**
```bash
cd admin
npm install && npm run dev
```

详细步骤见 `/README.md`。

---

## 5. 关键代码索引

- 蓝牙解析与上传：`蓝牙uniapp/store/modules/blueTooth.js:170 / :187 / :246`
- 应用工厂与蓝图注册（`create_app` + clinician/patient/device 三蓝图）：`back/config.py`；入口 `back/app.py`
- 医护认证（启用/登录/资料，bcrypt + JWT(clinician_id)）：`back/api/clinician.py`；口令哈希与签发：`back/auth.py`
- 鉴权（`token_required` 基于 `clinician_id`）：`back/utils.py`
- 患者与按患者历史（CRUD + `subject_id` + 分页/时间范围只读）：`back/api/patient.py`
- 设备与上传（蓝牙注册鞋垫 + 上传原始数据带 `patient_id`，归属 clinician+patient+device）：`back/api/device.py`
- SVM 推理（已抽出独立模块，`analyze()`；待异步解耦）：`back/api/analysis.py`
- 配置（DB 串与 `SECRET_KEY` 已改为读环境变量，模板见 `back/.env.example`）：`back/config.py`
- 后端地址（`baseURL`）：采集端 `蓝牙uniapp/config/index.js`；**管理台改 `admin/.env` 的 `VITE_BASE_URL`/`VITE_BASE_URL_PRO`（实际生效），`admin/src/config/index.js` 无人 import 是死配置**
- 数据表结构：`back/database_schema_mysql.sql`（唯一权威；旧 SQLite 版 `database_schema.sql` 已删）
