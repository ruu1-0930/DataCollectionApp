# AGENTS.md

本文件为 Codex 在本仓库后续开发时使用的基本约束与导航。**开始任何开发前，请先阅读架构方案。**

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
| 云后端 | `back/` | Flask + SQLAlchemy + PyJWT | clinician 鉴权与归属、设备摄取、临床步态只读 API、遗留 SVM 推理 |
| 数据库 | （远程 MySQL） | MySQL 5.7+ | clinician/患者/设备、每脚原始行、分析结果；另有隔离的官网 leads |
| 官网展示页 | `landing/` | 纯静态 HTML/CSS/原生 JS | 面向医生推广（根域 `sarcopenianus.com`）+ 留资表单 |
| ~~管理台~~ | ~~`admin/`~~ | Vue3 + Vite + UnoCSS | **🚫 已弃用**（见下） |

> **`admin/` 已弃用（2026-06-15）**：本仓库的采集流程仍为 **App-only**（操作员+患者均在采集端 App 上完成），管理台未启用、未部署。`D:\ME5001\Project` 的 Streamlit 医生工作台是独立只读客户端，不代表重新启用 `admin/`。除非 Ru1 明确重新激活，否则 `admin/` 不参与运行或维护。

环境要求：Python 3.7+、Node.js 14+、MySQL 5.7+。

---

## 2. 当前优先级（按架构方案的阶段推进）

### ADM01 全局只读业务管理员（2026-10-15）

Ru1已确认Project中的管理员Spec/Plan并选择Native顺序实施。A01新增Clinician.role，
clinician/admin_readonly二值、默认普通医生；新增/account/context，不改原登录/注册/me公开DTO或App。
管理员禁止旧患者/设备/资料写入及全部旧snapshot刷新入口；不以JWT中的role或页面按钮授权。
新增003_clinician_role.sql与服务器CLI account create-admin/set-role，隐藏口令与显式确认，
不在启动时创建/提权。所有验证只用隔离合成数据，003尚未在RDS执行，不称管理员已上线。
跨仓Spec/Plan/独立进度在Project `docs/superpowers/{specs,plans}/2026-10-15-sarcogait-admin-business-review*`。
每个完整交付集中验证、B实现后紧接Project进度提交；不重启旧admin、不改App或真实账号。

0. **🔴 进行中 — 迁移到自有云**：现有 ECS/数据库**均不在我方名下**（随时可能停机），迁到自有阿里云 **ECS + RDS**（同 VPC、RDS 不开公网）。**当前任务，先于阶段 1。** 因**尚未开始采集，无历史数据需迁移**，成本最低；迁移顺带完成阶段 1 的 HTTPS、收回 DB 公网、密钥/口令入环境变量（最后一项已完成）。逐步操作见 [迁移操作清单.md](迁移操作清单.md)；背景见架构方案阶段 0.5 与 FAQ 10.2。
   - **已完成**：ECS+RDS 开通、建库导 schema、gunicorn+systemd+nginx 部署跑通（公网 IP `118.31.39.47`）；三端地址改到新服务器；清理上一个开发者「捡漏/短剧」模板残留。
   - ✅ **域名 + HTTPS 已上线（2026-06-15）**：域名 `api.sarcopenianus.com`（备案通过，A 记录 → `118.31.39.47`），阿里云免费 DV 证书（DigiCert，有效期 **2026-06-15→09-12，3 个月，到期前需重签替换**）。nginx 切 443（80→443 跳转），证书在 ECS `/etc/nginx/ssl/`（私钥 chmod 600，**不入 git**），安全组放行 443。公网 `https://api.sarcopenianus.com` 证书可信、链路 `nginx(443)→gunicorn(5000)→Flask` 验证通过。采集端地址已切到 https：`蓝牙uniapp/config/index.js`、`utils/request.js`(`sslVerify:true`)。历史 admin 配置不再维护；配置模板见 `deploy/nginx-lanya.conf`。
   - **待办**：**HBuilderX 重打包 App**（https 地址打进 apk 才生效）；关 RDS 公网、复查安全组（5000 不对公网/22 仅对己）、下线旧机器；证书到期前续签。（admin 已弃用，无需部署）
1. **🟠 阶段 1 — 止血（部分完成）**：
   - ✅ **后端净重设（scope A，已完成）**：六表临床模型（clinicians/devices/patients/patient_pii/device_raw_data/device_transformed_data）+ 医护口令认证（bcrypt + JWT）+ 采集归属 clinician+patient+device + 按患者历史只读 API。子 agent 驱动 TDD，34 测试全绿。见 `back/` 与 `database_schema_mysql.sql`。
   - ✅ **App 端接入新接口（代码完成，scope A）**：分支 `feature/frontend-backend-alignment`。clinician 身份唯一键为 `(hospital, phone)`；启用提交医院/科室/姓名/手机号/口令，登录提交医院/姓名/手机号/口令。终端身份及运行时终端凭证已移除，旧本地 operator 残留会在读取时清理并回写；本次身份调整不做数据库迁移。`api/{clinician,patient,device}.js` 保持薄封装，`request.js` 以 `Bearer` JWT 鉴权，患者新建/选择、采集上传和按患者历史均已接后端。2026-08-13 源码扫描未发现运行时终端凭证，uni-app 自动化 `33 passed`。
   - ✅ **6→38 维全量落库（每脚一行，代码完成）**：一帧 BLE = 合并 38 字段（**固定前 19 左脚 / 后 19 右脚**），后端摄取拆成 L/R 两条每脚记录入库。`device_raw_data` 由「6 轴 IMU」扩为每脚 `foot`(L/R)+9 压力 `p1..p9`+6 IMU+4 步态（步长/步速/单支撑/双支撑，皆为设备固件输出，非本仓库模型计算；仅 SVM T1–T5 为推理）。改动文件：`models/models.py`、`database_schema_mysql.sql`、`migrations/001_raw_data_per_foot.sql`、`api/device.py`(38→2 行拆分 + 每脚跑 SVM)、`api/patient.py`(历史返回带 `foot`+全量压力/步态)；App `utils/apiShape.js` 的 `mapHistoryItem` 同步暴露 `foot`/`pressure`/步态。**后端 35 测试 + App 22 vitest 全绿**。`蓝牙uniapp` 上传侧无需改（已发 38 命名字段，拆分在后端）。
   - 🟡 **App 端真机回归（部分已验，2026-06-09）**：HBuilderX → 真后端 `http://118.31.39.47`。
      - ⏳ **设备路径待验**：新增设备流程已由**扫码改为蓝牙搜索附近设备**（修复了运行时权限未申请导致扫不到的问题，见 `store/modules/blueTooth.js` 的 `requestBlePermissions`/`syncBluetoothState`）；连接鞋垫、采集、上传落库与历史查询仍需真实设备和真实数据库回归。
     - ⏳ **待验**：连接鞋垫 → 采集 → 上传落库 + 归属（查 `device_raw_data` 每帧 L/R 两行 + `device_transformed_data` T1-T5 + `patients.last_collected_at`）、按患者查历史（数据页）。store/页面/蓝牙/网络无法 vitest mock，见 plan Task 12 手动清单。
   - HTTPS/密钥/收回公网随迁移完成。

### 临床步态数据工作台（跨仓只读链路，当前证据）

- **Agent v2 Stage 1 / T05（B snapshot HTTP）**：独立 `snapshot_bp` 提供 ensure、full、status、Agent projection、publication claim 五条接口。actor 仅取已校验 clinician JWT；所有快照读取经 T04 service 患者锁/归属检查。成功 DTO 复用严格 v1 schema，状态只返回 `SnapshotStatusV1` 五项元数据；全量历史读取仅显式 `include_superseded=true`。新接口错误统一严格 `ErrorEnvelopeV1`，旧 gait 端点和 token 行为不变。测试细节见架构方案 T05 小节；未做 MySQL/生产验证。
- **T05 审查修复轮 1**：snapshot POST body 限制为 2048 字节：已知 `Content-Length` 超限时读取前拒绝，未知/分块长度只读取至 2049 字节作判定；五条已知 snapshot 路径的错误方法返回严格 `400 invalid_request` envelope，旧端点 405 和未知路径 404 不变。定向 API 复测 `50 passed, 388 warnings`；未重跑完整 B。
- **T05 审查修复轮 2**：405 快照路径识别与 Flask 的 `<patient_id>` 字符串 converter 对齐，非正整数/非数字 ID 的错误方法也返回严格 envelope；定向 API `70 passed, 508 warnings`。不改变认证、I1 或旧路由行为。

- **T04 审查修复轮 1（I1）**：audit 时刻在患者事务锁内先量化到毫秒；同刻/回退时至少推进一毫秒，使 `DATETIME(3)` 落库精度、canonical 时间和患者内 hash-chain 顺序一致。SQLite 参数边界模拟 MySQL 舍入/截断，跨独立 Session/事务重载验证紧邻 hash 链接。仅复测 repository+service：`49 passed, 222 warnings in 7.01s`；无 schema/迁移变更，仍未在 MySQL 实库运行。

- **Agent v2 Stage 1 / T04（事务 snapshot 服务，隔离实现）**：`AnalysisSnapshotService` 提供 ensure/full/projection/claim，入口均验证 clinician/patient ownership。`AnalysisSnapshotRepository` 独立 Session + SQLite `BEGIN IMMEDIATE` / MySQL InnoDB `READ COMMITTED`、patient `FOR UPDATE` 协调；running attempt 先提交，分析不持写事务，并发仅返回 `snapshot_building`，无重复 analyzer 执行。发布前新事务重查来源；六字段 full identity 与独立 `(snapshot_id, projection_schema_version)` 子键分离，目前 projection 仅支持真实 v1。payload/hash 冻结，发布和审计共事务；supersession/state version/audit/outbox 原子提交，失效覆盖旧 revision 的所有快照。ensure/read/projection/claim **访问时同步**检查晚到数据；不声称上传时主动失效。中断 running attempt 不自动接管，须确认原执行终止后由后续恢复方案处理。T04 不含新路由、生产迁移、MySQL 实库或 outbox consumer。宿主 Python 3.14.4 + 隔离 `.test-deps` 合并验证 **263 passed, 883 warnings in 14.56s**；自审补齐 replacement 正反例后仅复测 repository **13 passed, 43 warnings in 2.50s**。命令和边界见架构方案 T04 小节。

- **T03 修复轮 1 验证**：本轮整项完成后仅运行受影响 `test_snapshot_pipeline.py`、`test_snapshot_models.py`、`test_gait_session_revision.py`，宿主 Python 3.14.4 + 隔离 `back/.test-deps`，结果 `221 passed, 700 warnings in 12.16s`。SQLite synthetic upload→revision→snapshot 证明四时间字段跨日 UTC、raw fingerprint 不变与重复 hash 稳定；无需重跑未改动全量。warnings 包含既有 utcnow/SQLite adapter/SVC/Query.get，新增端到端路径触发后两处 Query.get 提示。

- **T03 审查修复轮 1（C1 / I1–I3）**：DTO 边界将上传链路遗留 naive 时钟明确解释为 UTC+08:00 后转 UTC；aware 时钟正常 normalize，不改 raw 存储或 T02 指纹。所有 build 入口（含注入 loader）在 hash/filter 前核对冻结有序 IDs、计数、事件/摄取上下界、last accepted row 和 patient/device scope，拒绝 missing/extra/duplicate/out-of-order。withheld 保留 metric/reason 与压力聚合证据，全部解释 flags 输出 unknown，pressure attention level 抑制为 null。内部及公开 DTO 均严格记录五节点状态与 reason；evidence index 为 required，失败/空均 unavailable；pressure/chart failed/empty 明确降级。节点执行成功与 data_quality.gate 分离。M1 缺失数值审计保持 T08 范围，本轮不扩展；未部署、push 或修改上传协议。

- **Agent v2 Stage 1 / T01（隔离分支 `refactor/sarcogait-snapshot-v1`，仅持久化契约）**：B 在 `back/models/models.py` 新增七张 snapshot/revision/audit/outbox 表；`back/migrations/002_gait_snapshot_v1.sql` 为只向前的现有库 DDL，`back/database_schema_mysql.sql` 镜像绿场建表，`back/contracts/gait_snapshot_v1.schema.json` 提供五类严格 JSON Schema 2020-12 DTO。此提交未部署/执行生产迁移，不新增 API、服务或 Agent 数据流；原有六张临床表、38 字段摄取和只读链路保持原状。隔离 SQLite 的旧模型+新契约测试 `109 passed`；B 全量 `329 passed, 8 failed`，8 项全部是精确基线 `2413da4` 已带的孤立 `test_lead.py`（基线缺 `Lead`/路由）。MySQL 仅 dialect 编译/DDL 静态审计，未在 MySQL/RDS 执行。命令与边界见架构方案 T01 小节。
- **T01 审查修复轮 1**：`analysis_snapshot` 现在以 `(session_revision_id, patient_id)` 复合 FK 指向 `gait_session_revision(id, patient_id)`，拒绝两个单独有效但不同患者的 ID 组合；closed/superseded revision 的有序来源、行界/计数、事件/摄取时间和闭合证据由 DB 触发器冻结，身份始终不可改、冻结态不可退回 collecting。SQLite 相关模型契约复测 `137 passed, 657 warnings`；未重复跑未改动的全量套件。MySQL 仍待测试库执行验证。T03 应处理完整快照 DTO 中逐行 ID 列表的规模问题。
- **Agent v2 Stage 1 / T02（隔离分支 `refactor/sarcogait-snapshot-v1`，revision 物化）**：`back/services/canonical_json.py` 以 NFC、排序键、UTF-8 紧凑 JSON 和 decimal string 生成 SHA-256 输入；它拒绝任何 Python float，服务对源表 Float 用 `Decimal.from_float` 保留二进制存储精度，绝不套用 DTO 的六位展示舍入。`GaitSessionRevisionService` 先复用并校验 canonical patient/session ID，才查询 raw；按 `collected_at,id` 的 legacy 会话范围冻结同患者同设备的完整有序行，按 `uploaded_at`（两列均为服务器摄取时间，不冒称设备事件时间）记录可信接受边界。历史 gap 严格 `>30s`；latest 同设备所有患者均无新摄取满 `>=30s` 才闭合。范围内多设备返回 `scope_mismatch`，不静默丢行；晚到或重复行以新指纹创建 revision 并 supersede 旧 revision。`raw_rows_fingerprint` 是 T02/T03 共用的唯一 raw 指纹实现：有限 Float 保留二进制精度，None 与 NaN/±Infinity 仅在 raw 指纹中以明确类型标记表达，绝不进入 DTO。`gait.py` 仅复用这一 ID parser/formatter，未改 list/detail/frames/compare 或上传协议，未新增路由、repository 或生产迁移；T04 仍拥有事务/audit/outbox 的完整发布语义。
- **Agent v2 Stage 1 / T03（隔离分支 `refactor/sarcogait-snapshot-v1`，预发布确定性构建）**：`SnapshotPipeline` 对一个 closed revision 只作一次 revision-bounded raw load；它先计算 pre-filter raw fingerprint，再冻结 L/R 合法行并记录异常/排除，随后并发运行既有八指标、质量、完整 raw pressure 与 chart 节点，最后按固定顺序装配 full snapshot 和严格 Agent projection。metric/quality 执行失败或零可分析行使 build unavailable；limited/withheld 质量仍保留可追溯的有限证据，不能外推为可评分或疾病严重度。chart/pressure 失败降级为显式状态与 limitation。T03 的内部 build schema 没有 snapshot ID、published state 或创建时间；T04 才事务性补齐发布元数据并验证对外 DTO。完整 DTO 已移除 `ordered_row_ids`，冻结 revision 仍保存该列表；projection 不含 row/frame/device/chart/time-series。未新增 API、发布事务、数据库迁移或 Agent runtime。

- 当前链路是 `Project Streamlit -> Project FastAPI /api/clinical/* -> 本仓库 Flask /patients/*/gait/* -> device_raw_data`。A 原样透传当前 clinician Bearer JWT；B 校验 JWT，并在所有患者、会话、详情、逐帧和比较接口执行 clinician 归属检查。登录链路只使用医院、姓名、手机号、口令，不再使用终端身份；`enable`/`login` 仅接受精确 JSON 字段集，未知字段、`terminal_code`、非对象或畸形 JSON 返回 400，口令至少 4 字符且 UTF-8 编码不超过 72 字节。
- B 是规范数据源，负责 30 秒 gap 会话切分、稳定 session ID、8 个规范指标、数据质量、关注项、会话详情、最多 500 点图表序列、分页逐帧数据，以及同一患者 2–5 次会话比较。`gait_bp` 注册修复已提交为 `d3bf301`；步长始终保持固件语义 `step_length`，不得改称 stride length。`stride_time_cv_pct` 使用 `2 * step_length / walking_speed` 序列计算 CV，公式披露修复见 `ae3728c`。
- 当前 locked hardening：设备读写均受 clinician ownership 约束；登录限流为进程内原子 5/300（生产仍需网关或共享 limiter）；session ID 使用六微秒精度；详情 raw 查询保留同脚同时间戳重复行，logical-frame pagination 有边界。采集端 refresh 使用 single-flight、auth epoch 和 stale-navigation suppression；持久化 profile 仍不保存 passcode。最大压力差 marker 保留原始支持证据；A 仅接收 strict public clinician DTO，Redis 日志目标安全。
- 2026-07-25 工作台范围的最终 B 修复提交为 `57d306b`、`89ac8af`、`66db5ca`、`324d7c9`；A 修复提交为 `af26e14`、`c5ee7b0`、`f73f21d`，该历史范围的 broad review 已批准：`0 Critical / 0 Important / 0 Minor`。本节 2026-08-17 新增修复的 broad review 仍待完成。
- `back/services/pressure_analysis.py` 按完整会话、分脚汇总 `p1..p9`：仅有限且大于 0 的 ADC 样本进入均值，同时保留每个传感器的 `valid_samples`/`total_samples`。同一传感器左右脚各至少 3 个有效样本才进入 matched 集合；基于完整 matched 集合计算左右负载代理、负载占比和不对称度，并按 10%/20%/30% 给出研究性关注等级。详情压力汇总直接读取目标会话原始 per-foot 行，故同脚同时间戳的重复原始行不会在帧配对中丢失。ADC 尚未标定，不能换算物理压力，也不能据此给出疾病严重程度。
- 只有单会话详情 `GET /patients/<id>/gait/sessions/<session_id>` 暴露 `pressure_summary`；会话列表、比较和逐帧接口均省略该字段。详情压力汇总使用目标会话的有界批量查询；列表/比较不读取压力传感器列，逐帧仍按分页边界读取。
- 采集端安全修复提交为 `ff4d693`、`94d4cfb`、`27bad49`、`62d807e`：持久化 operator profile 不保存 passcode，`runtimePasscode` 只存在于运行期 Pinia 状态；`reset` 与启动未解锁分支都会清 JWT；请求生命周期日志只记录 URL、方法、状态和错误类别，不记录口令、JWT、PII 或原始传感器载荷；解锁提交有并发门。
- 当前自动化证据：B full `226 passed`；uni-app `64 passed`；A Redis `20 passed`；A clinical/UI `334 passed`，仅 1 条既有 Starlette `python_multipart` warning；Harness boundary `577 passed`。源码运行时终端凭证扫描和 diff-check 均干净。
- comparison recent-five per-metric median 契约已关闭：所有 metric 共用最近最多五个 complete/usable 历史会话窗口，保留有限 0；每 metric 在固定窗口内忽略 unavailable；该基线与 first-selected delta baseline 分离。B 分批向前扫描，直到五个合格会话或历史耗尽，不使用固定候选截断。
- 已关闭边界包括：NaN/Inf fail closed；strict canonical 8 metrics/flags；SQL frame pagination 与有界历史；400/404/422；inclusive end date/reverse range；late-401 pending reset；`delta_abs`/`delta_pct`；9-point pressure time series + raw IMU magnitude；canonical ID；30s gap。
- 本地浏览器 QA 使用隔离的一次性 SQLite，运行真实 B Flask、A FastAPI 与 Streamlit；验证了四字段登录、1 个患者/2 次采集会话、会话均值足压、单帧足压、IMU 以及会话切换重置，并覆盖 1440x900 与 390x844。多选状态仅由真实 Streamlit AppTest 验证为 `[] -> [S1] -> [S1, S2]`，不声称比较图已完成浏览器验证。QA 后临时数据库已删除，相关本地服务已停止。
- 上述本地证据不得外推为 RDS、真实鞋垫、生产三服务链路或真实多 clinician ownership 已验证；压力 ADC 标定也未完成。仍需在真实设备、真实数据库和生产部署路径上做纵向验证。
- Task 8 的本地实现、修复、验证和文档提交已完成；最终跨仓 broad specification/code-quality review 尚未完成，因此不得称 Task 8 已完全关闭。
- AI Agent、MCP、memory 仍不在当前阶段；跌倒检测仍只是报告，未实现。
- 跌倒检测调研已完成于 `docs/fall-detection-feasibility.md`；采样率仍是阻塞项，本阶段没有实现跌倒检测。
### 2.2 并行线 — 官网展示页（面向医生推广，代码完成）

- **目标**：给根域 `sarcopenianus.com` 做一个 Apple 式简约高级单页展示页，向医生推广步态采集系统；含系统/能力详解、未来路线、留资/预约演示表单、科研合作联系入口。
- **状态**：✅ 代码完成（视觉稿经用户确认；浅色临床高级风 + 单一科技蓝 `#2b6cff`）。
- **前端（新）**：`landing/{index.html,styles.css,main.js}` —— 纯静态、无构建、滚动渐入、CSS/SVG 足压热力图手机框示意；留资表单 `fetch` 提交（本地 localhost 走 `127.0.0.1:5000`，线上走 `https://api.sarcopenianus.com`）。
- **后端（新/改）**：留资接口 `back/api/lead.py`（公开 `POST /leads` + 蜜罐反垃圾；受保护 `GET /leads` 复用 `token_required`），`Lead` 模型（`models/models.py`，`leads` 表，非患者 PII、无外键、与临床数据隔离），`config.py` 注册 `lead_bp`，schema 同步 `database_schema_mysql.sql` + 迁移 `migrations/001_leads.sql`，测试 `tests/test_lead.py`。
- **部署（新）**：`deploy/nginx-site.conf`（根域 + www 静态托管，与 `nginx-lanya.conf` 并存）。**待办**：根域/www 的 DNS 解析 + HTTPS 证书（现 DV 证书只签了 `api.` 子域）；landing 部署到 ECS `/opt/lanya/landing/`；确认备案覆盖根域。
- **范围边界**：截图/图表用示意素材（占位），不接真实患者数据；不引前端框架；中文为主。
- **未来路线（展示页 #road 已写入）**：可靠采集 → 科研分析侧 → 更强模型 → **AI 智能体辅助诊断（引入智能体，综合步态数据与多科室检查报告，输出结构化评估与诊断建议，辅助医生决策，非替代诊断）** → 数字生物标志物平台愿景。详见云迁移 memory 的 agent 功能方向。

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
- 每次执行完任务之后，同步更新维护 `AGENTS.md` 以及 `系统架构方案.md`，记录最新进展和已完成工作。

### 3.4 临床工作台所有权边界

- 2026-10-14 Ru1授权整理已实现代码并push供ECS更新；确认RDS未做002快照迁移。sensor-v2既有增量集中103passed/227warnings/13.57s，只有合成SQLite；本轮不执行RDS迁移或服务器更新，不合并main/force。发布清单见docs/releases/2026-10-14-snapshot-workbench.md，已有001假设空表不能在真实数据上直接重跑。

- 2026-10-08 D21（Project联动）补齐SnapshotV1既有chart三字段：每帧每脚九点ADC均值包含零，缺点/非有限/负值/无法表示则该值null；双脚分别ax/ay/az模长再取均值，缺脚/轴留空，不混角速度。仍最多前500帧。共享分析器版本为`snapshot-pipeline-v2`，新ensure创建新版本identity，旧payload/报告不回填；schema/projection形状与评分指标不改。
- 本地集中B172passed、极值审查修复后sensor11passed；实际B→Project BFF→页面组件通过、限域独立审查闭环。没有MySQL/设备/浏览器/临床验收或模型调用，Lead/隐私旧基线不扩测。准确命令与缺失/极值/新旧版本证据在Project `docs/agent-v2/sensor-display-verification-2026-10-08.md`。UI单帧仍独立raw接口，不进入Agent证据；完整六轴时序未扩展。
- B 只从 `device_raw_data` 的每脚原始行生成规范会话与指标；规范 keys 为 `walking_speed_mps`、`step_length_m`、`single_support_time_s`、`double_support_time_s`、`cadence_spm`、`step_length_asymmetry_pct`、`stride_time_cv_pct`、`double_support_ratio_pct`。
- B 拥有会话切分、数据质量、证据/关注项、稳定 ID、详情、逐帧分页和比较语义；修改这些契约时先改 B 测试，再同步 A 的严格 DTO。
- A 只拥有 typed client、`/api/clinical/*` BFF 和 clinician UI；B 不为 A 新增本地数据库、Excel 或 Agent 兼容层。
- Harness/MCP 重定向、clinician memory、多学科 agents 和 AI chat 均在数据工作台之后。Harness 包边界保持 `packages/harness/sarcogait_harness/` 不得 import `app.*`。

---

## 4. 本地运行

**后端**
```powershell
cd D:\ME5001\DataCollectionApp\back
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# DB/SECRET_KEY 只放未跟踪的 .env；不要改 config.py 写入真实值
.\venv\Scripts\python.exe app.py
```

**B 临床步态契约与全量回归**
```powershell
cd D:\ME5001\DataCollectionApp\back
.\venv\Scripts\python.exe -m pytest tests\test_gait_analysis.py tests\test_gait_comparison.py tests\test_gait_api.py -q
.\venv\Scripts\python.exe -m pytest -q
```

结果末行中的 `passed` 是通过数，`failed`/`errors` 必须为 0；warning 需按上文已知类别核对，新增类别要先调查。

**采集端 App（uni-app）**
```bash
cd 蓝牙uniapp
# 用 HBuilderX 打开，运行到 Android 真机（蓝牙原生模块需真机/自定义基座）
# 修改 config/index.js 的 baseURL 指向你的后端
```

**管理台**：🚫 已弃用，不再运行/部署（见第 1 节说明）。

详细步骤见 `/README.md`。

---

## 5. 关键代码索引

- 蓝牙解析与上传：`蓝牙uniapp/store/modules/blueTooth.js:170 / :187 / :246`
- 应用工厂与全部蓝图注册（当前含 clinician/patient/device/gait/lead）：`back/config.py`；入口 `back/app.py`
- 医护认证（启用/登录/资料，bcrypt + JWT(clinician_id)）：`back/api/clinician.py`；口令哈希与签发：`back/auth.py`
- 鉴权（`token_required` 基于 `clinician_id`）：`back/utils.py`
- 患者与按患者历史（CRUD + `subject_id` + 分页/时间范围只读）：`back/api/patient.py`
- 设备与上传（蓝牙注册鞋垫 + 上传原始数据带 `patient_id`，归属 clinician+patient+device）：`back/api/device.py`
- SVM 推理（已抽出独立模块，`analyze()`；待异步解耦）：`back/api/analysis.py`
- 官网留资接口（公开 `POST /leads` + 蜜罐，受保护 `GET /leads`）：`back/api/lead.py`；`Lead` 模型：`back/models/models.py`
- 官网展示页（纯静态）：`landing/`；nginx 根域托管模板：`deploy/nginx-site.conf`
- 配置（DB 串与 `SECRET_KEY` 已改为读环境变量，模板见 `back/.env.example`）：`back/config.py`
- 后端地址（`baseURL`）：采集端 `蓝牙uniapp/config/index.js`（当前 `https://api.sarcopenianus.com`）。（管理台 admin 已弃用，其地址配置不再维护）
- 数据表结构：`back/database_schema_mysql.sql`（唯一权威；旧 SQLite 版 `database_schema.sql` 已删）
- 临床步态规范逻辑：`back/services/gait_analysis.py`、`back/services/gait_comparison.py`、`back/services/gait_thresholds.py`
- 临床步态只读接口与归属检查：`back/api/gait.py`；蓝图注册：`back/config.py`
- 跌倒检测可行性报告（仅调研，未实现）：`docs/fall-detection-feasibility.md`
- 数据查询门户（Metabase 只读 BI，公网 `https://data.sarcopenianus.com`）：部署资产 `deploy/nginx-data.conf`、`deploy/metabase/{docker-compose.yml,.env.example,README.md}`；设计/计划 `docs/superpowers/{specs,plans}/2026-06-24-metabase-data-query-portal*.md`。两个只读数据库账号 `mb_ro_full`(含PII)/`mb_ro_deid`(脱敏)，元数据库 `metabase`。采集端 App 与 back/ 零改动。

---

## 6. Claude Code 迁移档案

- 原始 Claude 自动记忆：`D:\OneDrive\文档\CLAUDE 清理\archive\claude-code\memories\D--ME5001\`
- 当前跨系统交接报告：`D:\OneDrive\文档\CLAUDE 清理\archive\claude-code\plans\agent-ai-replicated-dahl.md`
- 当前 Agent 适配计划：`D:\OneDrive\文档\CLAUDE 清理\archive\claude-code\plans\stateful-hopping-hippo.md`
- 官网展示页历史计划：`D:\OneDrive\文档\CLAUDE 清理\archive\claude-code\plans\app-parallel-quasar.md`

以上档案用于追溯；当前代码、测试和本仓库文档优先于历史会话内容。
