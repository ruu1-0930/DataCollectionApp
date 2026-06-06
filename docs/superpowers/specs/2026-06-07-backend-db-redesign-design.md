# 后端 + 数据库重构设计（scope A：先跑通采集）

- 日期：2026-06-07
- 状态：设计定稿，待用户复核
- 关联：前端改版（`docs/superpowers/specs/2026-06-06-frontend-redesign-design.md`，已上线 PR #1）、`系统架构方案.md` 阶段 1、`CLAUDE.md` 第 3 节红线

## 1. 背景与目标

前端已改为「**设备级一次性启用（医院/科室/医生/联系方式 + 自设口令）→ 解锁 → 选/建患者 → 当前患者上下文**」的临床多患者模型，但当前后端仍是旧的「单用户 + 无密码登录 + role 0/1/2 + 6 维落库」模型，与前端完全不匹配，且违反多条医疗数据红线。

本次重构目标：**让后端与新临床模型对齐，先把数据采集端到端跑通**——医护账户带真实口令鉴权、患者表带全局假名 `subject_id`、采集数据可靠归属到「医护 + 患者 + 鞋垫设备」、支持按患者查历史。PII 与传感器数据分表。

**绿场前提**：尚未开始采集，无历史数据需迁移，可净重设 schema（不需要 ALTER 兼容旧数据）。

## 2. 范围（scope A）

### 2.1 本次实现
- 净重设数据库：废弃旧表，建医护/患者/PII/设备/原始数据/分析数据 6 张表。
- 医护口令认证：启用注册医护账户（口令 bcrypt 哈希），服务端签发 JWT；所有采集接口走 token 鉴权（不再无密码签发）。
- 患者管理：新建/列出/详情，后端全局派发 `subject_id`，phone 必填且同医护下查重。
- 采集上传：带 `patient_id`，归属到医护 + 患者 + 设备。
- 按患者历史只读 API。
- 鞋垫设备：通过**蓝牙连接**注册（非扫码）。

### 2.2 明确延后（后续 spec，不在本次）
- 6 → 38 维全字段落库（本次仍存 6 维：ax/ay/az/gx/gy/gz）。
- 批量上传 / 采集会话 / 离线重传。
- 实验室只读 API + 去标识化导出。
- SVM 推理异步化（本次维持上传请求内联跑）。
- `admin/` 管理台重做（本次管理台暂停用）。

## 3. 数据模型（净重设）

废弃并删除：旧 `users`、旧 `devices`(user_id 外键)、`weekly_schedules`、role(0/1/2) 体系、`admin.py` 所依赖的旧表。

新建 6 张表：

### 3.1 `clinicians`（医护账户，启用时创建）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| hospital | varchar | 医院 |
| dept | varchar | 科室 |
| name | varchar | 医生姓名 |
| phone | varchar | 联系方式，登录定位用 |
| terminal_code | varchar | **手机/App 终端标识**（启用时 App 生成并持久化、上报），与 phone 一起定位医护 |
| passcode_hash | varchar | 自设口令的 **bcrypt 哈希**（红线：禁止明文） |
| created_at | datetime | |

- 唯一约束：`(phone, terminal_code)`，避免同手机同终端重复注册；换机即新 terminal_code。

### 3.2 `devices`（蓝牙鞋垫硬件，蓝牙连接时注册）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| device_code | varchar unique | 鞋垫硬件编码（蓝牙连接获得） |
| device_name | varchar | |
| is_enabled | bool | |
| clinician_id | FK→clinicians | 归属医护 |
| created_at | datetime | |

### 3.3 `patients`（去标识化主体，不含 PII）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| clinician_id | FK→clinicians | 患者属于医护 |
| subject_id | varchar unique | **后端全局派发**的假名，如 `#00427`（导出只用它） |
| gender | varchar | 非身份字段 |
| age | int | 非身份字段 |
| created_at | datetime | |
| last_collected_at | datetime | 最近采集时间 |

### 3.4 `patient_pii`（PII 单独表，导出永不 join）
| 字段 | 类型 | 说明 |
|---|---|---|
| patient_id | PK / FK→patients | 1:1 |
| name | varchar | |
| phone | varchar | 必填，同医护下查重依据 |
| email | varchar | 可空 |
| address | varchar | 可空 |

### 3.5 `device_raw_data`（原始数据，append-only）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| device_id | FK→devices | 哪只鞋垫 |
| patient_id | FK→patients | 哪个患者 |
| clinician_id | FK→clinicians | 哪个医护（冗余，便于按医护/患者查询与导出） |
| ax, ay, az, gx, gy, gz | float | **scope A 暂存 6 维**，38 维扩展延后 |
| collected_at | datetime | 采集时间（设备/采集时刻） |
| uploaded_at | datetime | 落库时间 |

- 红线：raw 只增不改（append-only）。

### 3.6 `device_transformed_data`（SVM 结果，可重算）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| raw_data_id | FK→device_raw_data | |
| T1, T2, T3, T4, T5 | float | SVM 推理输出 |
| created_at | datetime | |

### 3.7 索引
- `clinicians(phone, terminal_code)` 唯一；`devices(device_code)` 唯一；`patients(subject_id)` 唯一。
- 外键列建索引：`devices.clinician_id`、`patients.clinician_id`、`device_raw_data.(device_id, patient_id, clinician_id)`、`device_transformed_data.raw_data_id`。
- `device_raw_data(patient_id, collected_at)` 复合索引，支撑按患者历史的时间范围分页查询。

## 4. 认证与流程

### 4.1 启用（首次）
1. App 首次启用：生成并持久化 `terminal_code`（本地 uuid 或系统 deviceId），收集医院/科室/医生/手机 + 自设口令。
2. POST `/clinician/enable` → 后端建 `clinicians`（口令 bcrypt 哈希），返回 JWT `{clinician_id, exp}`。
3. App 存 token + terminal_code。

### 4.2 解锁（日常）
- 本地校验口令（离线可用，不走后端）。token 复用。

### 4.3 token 过期 / 401 兜底
- App 静默调 POST `/clinician/login`（phone + terminal_code + 口令 → 校验 bcrypt hash → 新 JWT）刷新。这是唯一「解锁相关走后端」的路径。

### 4.4 采集接口鉴权
- 所有采集/患者/设备接口走 `@token_required`，从 token 取 `clinician_id`，数据归属由此而来。**不再无密码签发 token。**

## 5. API（仅 scope A 流程所需）

| 方法 | 路径 | 鉴权 | 作用 |
|---|---|---|---|
| POST | `/clinician/enable` | 无（注册） | 启用注册医护，口令哈希入库，返回 token |
| POST | `/clinician/login` | 无（校验口令） | phone + terminal_code + 口令 → 校验 → 新 token |
| GET | `/clinician/me` | token | 读医护资料 |
| PUT | `/clinician/me` | token | 改医护资料（口令修改单独流程，本次可选） |
| GET | `/patients` | token | 当前医护的患者列表 |
| POST | `/patients` | token | 新建患者：phone 必填，同医护下按 phone 查重（重复返回已存在患者），后端派发 subject_id；PII 入 `patient_pii` |
| GET | `/patients/<id>` | token | 患者详情（限本医护） |
| GET | `/patients/<id>/data` | token | **按患者历史只读**，支持时间范围 + 分页 |
| GET | `/devices` | token | 当前医护的鞋垫列表 |
| POST | `/devices` | token | 蓝牙连接成功后注册鞋垫（App 上报 device_code），归属当前医护 |
| DELETE | `/devices/<id>` | token | 删除鞋垫（限本医护） |
| POST | `/devices/<device_code>/raw_data` | token | 上传原始数据，body 带 `patient_id`，落库并归属 clinician+patient+device；内联跑 SVM 写 `device_transformed_data` |

- 响应包络沿用现有 `Response.success/error`（`{code, msg, data}`）。
- 越权防护：所有「限本医护」接口校验资源 `clinician_id == g.clinician_id`，越权返回 403。

## 6. 安全与红线对齐

- ✅ 口令 bcrypt 哈希，不存明文；不再无密码签发 token。
- ✅ 患者 PII（name/phone/email/address）独立 `patient_pii` 表，传感器数据只引 `patient_id`，导出默认只用 `subject_id`。
- ✅ raw 数据 append-only；分析结果单独表、可重算。
- ✅ 密钥/DB 口令继续走环境变量（沿用现有 `back/.env` + `create_app()`）。
- ⏭ HTTPS / 收回 DB 公网：随云迁移完成（架构方案阶段 0/1），非本 spec 代码范围。
- ⏭ 上传轻量化（推理异步）：本次维持内联，异步化延后。

## 7. 受影响文件（实现时）

- `back/database_schema_mysql.sql`：重写为新 6 表（唯一权威）。
- `back/models/models.py`：重写 SQLAlchemy 模型。
- `back/api/user.py` → 替换为 `back/api/clinician.py`（enable/login/me）。
- `back/api/device.py`：改造设备/采集/历史接口，归属链改为 clinician+patient+device；保留 SVM 内联。
- `back/api/admin.py`、`back/api/weekly_schedule.py`：本次停用/删除（管理台重做延后）。
- `back/app.py`：更新蓝图注册。
- `back/utils.py`：`token_required` 改为基于 `clinician_id`（`g.clinician_id`），去掉 role。
- 新增依赖：bcrypt（或 passlib）。

## 8. 验收标准（scope A）

1. 全新空库执行新 schema 可建表成功。
2. App 启用 → 后端建医护、返回可用 token；用错口令 `/clinician/login` 拒签。
3. 新建患者：phone 必填校验生效；同医护下重复 phone 命中已存在患者；后端返回全局唯一 `subject_id`。
4. 蓝牙连接后注册鞋垫成功并归属当前医护。
5. 上传原始数据落库，正确关联 clinician+patient+device，并产生 T1–T5。
6. `/patients/<id>/data` 能按患者拉到历史，支持时间范围与分页，且只能拿到本医护的患者。
7. 无 token / 错 token 的采集请求被拒（鉴权红线）。
8. `database_schema_mysql.sql` 与模型一致。

## 9. 开放问题 / 后续

- 口令找回/修改流程（App 重装丢失本地态）：本次仅做基础修改入口，重装恢复属边缘场景，延后。
- `admin/` 管理台与新模型的对接：延后单独 spec。
- 38 维落库需与硬件团队核对字段顺序后再做。
