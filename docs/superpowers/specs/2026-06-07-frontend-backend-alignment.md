# 前后端对齐清单（后端重构 scope A）

- 日期：2026-06-07
- 配套设计：`2026-06-07-backend-db-redesign-design.md`
- 用途：列出后端重构后，**采集端 App 必须同步改动的接触点**与**前后端接口契约**。前端现状几乎全是本地存储（operatorStore / patientStore / clinicStorage），接真后端时需要逐项改。

> 说明：本清单中标 **[需改前端]** 的项是 App 侧要动的代码；标 **[契约]** 的是双方约定的请求/响应格式。前端真实接入与后端实现一并在 writing-plans 里排期（可能拆成「后端实现」+「前端接入」两段任务）。

---

## 1. 终端标识 terminal_code（新增）

- **[需改前端]** 当前 `operatorStore` / `clinicStorage` **没有 terminal_code**。需在首次启用时生成一个稳定标识并本地持久化（`uni.getSystemInfoSync().deviceId` 或自生成 uuid 存 storage），随启用/登录上报后端。
- 换机/重装会产生新 terminal_code（视为新终端），属可接受的边缘行为。

## 2. 启用流程（本地 → 走后端）

- 现状：`operatorStore.enable({hospital,dept,name,phone,passcode})` 仅写本地，`enabled:true`。
- **[需改前端]** enable 改为：先生成 terminal_code → POST `/clinician/enable` → 成功后用 `setToken()` 存返回的 JWT，再写本地 operator 档案。
- **[契约]** `POST /clinician/enable`
  - 请求：`{ hospital, dept, name, phone, terminal_code, passcode }`（passcode 明文经 HTTPS 传输，后端 bcrypt 哈希）
  - 响应 data：`{ token, clinician: { id, hospital, dept, name, phone } }`
- **注意**：启用需要网络（要建账户、拿 token）。离线无法首次启用——前端在启用页要有网络失败提示。
- **口令双重用途**：口令既本地存（用于离线解锁，见第 3 节），又在 enable/login 时发给后端校验。

## 3. 解锁与 token 刷新

- 现状：`operatorStore.unlock(passcode)` 纯本地比对。**保留本地解锁**（离线可用）。
- **[需改前端]** token 过期 / 接口返回 401 时，App 静默用本地存的 `phone + terminal_code + passcode` 调 `/clinician/login` 换新 token 重试，**不**弹登录页、不清本地临床数据（沿用现有 request.js「不强制登出」策略）。
- **[契约]** `POST /clinician/login`
  - 请求：`{ phone, terminal_code, passcode }`
  - 响应 data：`{ token, clinician: {...} }`；口令错误 → 后端非 200，前端提示但不登出。

## 4. 患者：subject_id 改由后端发（重点）

- 现状：`patientStore.create` 本地 `nextSeq` + `formatSubjectId(seq)` 生成 `#00427`，`currentId` getter 也用本地 seq 算 subject_id。
- **[需改前端]**：
  - 新建患者改为 POST `/patients`，**用后端返回的 `id` 和 `subject_id`**，不再本地生成。
  - 当前患者上下文从「本地 seq」改为「后端 patient_id」。`currentId` 直接用后端 `subject_id`。
  - 患者列表 `list()` 改为 GET `/patients`（仍可本地缓存做离线展示，但权威以后端为准）。
  - phone 必填校验放前端（后端也校验）。
  - **查重交互**：同医护下 phone 重复时，后端返回**已存在的患者**（非报错）；前端需识别并提示「该患者已存在，已为你选中」。
- **[契约]** `POST /patients`
  - 请求：`{ name, phone, gender, age }`（phone 必填）
  - 响应 data：`{ id, subject_id, gender, age, name, phone, created_at, last_collected_at }`；若命中查重，返回既有患者并带标记（如 `existed: true`）。
- **[契约]** `GET /patients` → data: `[{ id, subject_id, name, phone, gender, age, last_collected_at, count? }]`（仅当前医护）。
- **[契约]** `GET /patients/<id>` → 患者详情（限本医护，越权 403）。

## 5. 采集上传：补 patient_id（重点）

- 现状：`blueTooth.js:246` `sendDeviceRawDataApi(device.device_code, apiData)` —— **没带 patient_id**，无法归属患者。
- **[需改前端]** 上传时带上当前患者 `patient_id`（从 patientStore 当前上下文取）。无当前患者时禁止/暂存采集。
- **38 字段说明**：前端 `apiData` **已包含全部 38 维**（`blueTooth.js:187-243`：lp1-9 / 左脚 ax..gz / 左脚步态 / rp1-9 / 右脚 right_* / 右脚步态）。**scope A 后端仍只落 6 维（ax/ay/az/gx/gy/gz），其余字段后端先忽略**——前端无需删字段，38→全量落库在后续 spec 打开后端即可接住。
- **[契约]** `POST /devices/<device_code>/raw_data`
  - 请求：`{ patient_id, ...apiData(38 维) }`
  - 行为：后端按当前 token 的 clinician_id + body 的 patient_id + 路径 device_code 归属落库（scope A 存 6 维），内联跑 SVM 写 T1–T5。
  - 响应 data：落库后的 raw + transformed 摘要（按需）。

## 6. 鞋垫设备：蓝牙连接时注册

- 现状：`addUserDeviceListApi`（POST `/devices`）已存在；设备列表 `getUserDeviceListApi`（GET `/devices`）。
- **[需改前端]** 设备归属由 user 改为 clinician（后端按 token 处理，前端 payload 不变或微调）。蓝牙连接成功后（`blueTooth.js` 连接回调里）若是新设备则 POST `/devices` 注册 `device_code`。**非扫码**。
- **[契约]** `POST /devices` 请求：`{ device_code, device_name? }`；响应 data：`{ id, device_code, device_name, is_enabled }`。
- **[契约]** `GET /devices` → 当前医护的设备列表；`DELETE /devices/<id>` 删除（限本医护）。

## 7. 按患者历史只读

- **[需改前端]** 数据页 / 患者详情拉历史改为 GET `/patients/<id>/data`（替代现按设备/按用户的取数）。
- **[契约]** `GET /patients/<id>/data?start=&end=&page=&page_size=`
  - 响应 data：`{ items: [{ id, collected_at, ax,ay,az,gx,gy,gz, transformed: {T1..T5} }], total, page, page_size }`

## 8. 作废 / 变更的旧接口（前端要清理）

现 `api/user.js` 里以下函数对应的后端接口在 scope A **作废或更名**，前端需同步删除/改写调用方：

| 旧前端 API | 旧路径 | scope A 处置 |
|---|---|---|
| `userLoginApi` | `/login` | 删除（改 `/clinician/login`） |
| `userRegisterApi` | `/register` | 删除（改 `/clinician/enable`） |
| `userUpdateApi` | `/user` PUT | 改 `/clinician/me` PUT |
| `getUserWeekPlanApi` | `/weekly-schedules` | **删除**（周计划随旧模型废弃） |
| `getDeviceDataApi` | `/devices/<code>/data` | 改为按患者 `/patients/<id>/data` |
| `getDeviceLatestT1T2Api` | `/devices/latest_t1_t2` | 复核去留（首页实时区是否还用） |
| `getUserT2T3Api` | `/devices/statistics` | 复核去留（数据页统计） |
| `getDeviceDailyAveragesApi` | `/devices/daily_averages` | 复核去留 |
| `userAvatarUploadApi` | `/upload_avatar` | 复核（医护是否需要头像） |

> 「复核去留」的几项取决于前端首页/数据页改版后还用不用对应数据；writing-plans 阶段逐个对照页面确认，能删则删，避免留死接口。

## 9. 字段名映射对照

| 前端（现） | 后端（新） | 备注 |
|---|---|---|
| operator.name | clinicians.name | 医生姓名 |
| operator.hospital/dept/phone | clinicians.hospital/dept/phone | |
| operator.passcode | clinicians.passcode_hash | 前端发明文，后端哈希；前端本地仍存明文供离线解锁 |
| （无） | clinicians.terminal_code | 新增，前端要生成 |
| patient.seq + formatSubjectId | patients.subject_id | **改由后端发** |
| patient.name/phone | patient_pii.name/phone | PII 分表（前端无感，仍当普通字段收发） |
| patient.gender/age | patients.gender/age | |
| attribution(){hospital,dept,doctor} | 由 token 的 clinician 推导 | 上传不再单独带归属串，后端按 token 归属 |

## 10. 不变项（确认对齐）

- 响应包络 `{ code, msg, data }` 不变；request.js 响应拦截器 `code===200` 取 `data.data`、401 仅提示不登出——沿用。
- 首页足底压力图（foot.png + 蓝点 ripple）原实现不动。
- token 存取沿用 `utils/auth.js` 的 `setToken/getToken`。

---

## 11. 落地状态复核（2026-06-07）

> 复核口径：逐项对照现后端 `back/api/*.py` 与现前端 `蓝牙uniapp/`。结论——**后端 scope A 已实现且与本清单契约高度一致；前端尚未动工，全部 `[需改前端]` 项待办（grep `terminal_code`/`patient_id`/`clinician/enable`/`/patients` 在前端命中 0）。** 对齐的剩余工作量几乎全在前端。

### 11.1 契约符合度（后端，已实现）

| 节 | 后端实现位置 | 与契约 |
|---|---|---|
| §2 enable | `back/api/clinician.py:15` | ✅ 字段/响应一致；额外做同手机同终端**幂等重发 token 且仍校验口令**（红线 §3.2） |
| §3 login | `back/api/clinician.py:44` | ✅ `{phone,terminal_code,passcode}`→`{token,clinician}` |
| §8 me PUT | `back/api/clinician.py:67` | ✅ `/clinician/me` GET/PUT |
| §4 患者 | `back/api/patient.py` | ✅ POST/GET/GET`<id>`；查重返回既有患者带 `existed:true`；`subject_id` 后端发（`#%05d`） |
| §5 上传 | `back/api/device.py:61` | ✅ `patient_id` 必填、归属 clinician+patient+device、落 6 维、内联 SVM；响应 `{raw_data_id, transformed:{T1..T5}}` |
| §6 设备 | `back/api/device.py:17/41/48` | ✅ POST/GET/DELETE `/devices`，按 token 归属 clinician |
| §7 历史 | `back/api/patient.py:69` | ✅ `?start=&end=&page=&page_size=`，越权 403 |
| token | `back/utils.py:18` | 后端要求 `Authorization: Bearer <token>` |

### 11.2 前端待办（全部未动工）

| 节 | 现状文件 | 缺口 |
|---|---|---|
| §1 | `utils/clinicStorage.js`、`store/modules/operator.js` | 无 terminal_code 字段，无生成/持久化逻辑 |
| §2 | `store/modules/operator.js:15` | `enable()` 纯本地写，未调后端、未存 token |
| §3 | `utils/request.js` | 无 401 静默换 token 重试；本地 `unlock()` 已符合（保留） |
| §4 | `store/modules/patient.js`、`utils/patient.js`、`pages/patient/*` | 仍本地 `seq`+`formatSubjectId`；`new.vue` 还在创建前预览编号；`select.vue` 按 `seq` 取数 |
| §5 | `store/modules/blueTooth.js:246` | `sendDeviceRawDataApi(device_code, apiData)` 不带 `patient_id`，无「无当前患者禁采」 |
| §7 | `pages/data/data.vue` | 全是示意数据，未拉 `/patients/<id>/data` |
| §8 | `api/user.js`、`api/index.js` | 旧接口函数全在，无任何 clinician/patient 新接口函数 |

### 11.3 复核新发现的落地细节（写进 plan）

1. **request.js 鉴权白名单**：`utils/request.js:100` 仅放行 `/login`、`/register` 的无 token 请求，其余无 token 直接 `Promise.reject`。**enable/login 改用新路径后，必须把 `/clinician/enable`、`/clinician/login` 加入白名单**，否则首启拿不到 token 的请求会被拦截。
2. **token 来源单一化**：`request.js:96` 现从 `useUserStore().token` 读 token（旧登录模型）。新模型 token 由 operator 启用/登录产生，建议拦截器改为直接读 `utils/auth.js` 的 `getToken()`，与产生方解耦；保存格式沿用现约定的 `"Bearer xxx"` 整串（后端按空格切分取第 2 段）。
3. **§6 设备接口已对齐，保留扫码加设备**：现前端 `addUserDeviceListApi`(POST `/devices`)/`getUserDeviceListApi`(GET)/`deleteDeviceApi`(DELETE `/devices/<id>`) 与新后端契约**已一致**，`mine.vue` 扫码加设备 → `blueTooth.addDevice()` 流程在 token 就绪后即可直接工作。**本清单 §6「蓝牙连接时注册/非扫码」属交互偏好，非对齐必需**——为遵循既有可用流程与 YAGNI，**plan 不强行重做为连接时注册**，仅在数据归属正确的前提下沿用扫码加设备；连接时自动注册列为可选后续优化。
4. **患者数据形状变更的连带改动**：患者对象由 `{seq,...}` 改为 `{id, subject_id, name, phone, gender, age, last_collected_at}` 后，`utils/patient.js` 的 `formatSubjectId`/`nextSeq` 不再用于发号（仅旧测试保留），`searchPatients`/`maskPhone`/`validatePatient` 仍复用；`new.vue` 取消「创建前预览编号」（编号改由后端创建后返回），`select.vue`/`CaPatientBar` 改用 `subject_id` 与后端 `id`。

### 11.4 测试现实（影响 plan 的 TDD 粒度）

- 前端测试基建 = 纯 `vitest`（`tests/patient.test.js` 仅测 `utils/patient.js` 纯函数），**无 uni/BLE 原生模块的 mock**。
- 故 plan 中：**可抽成纯函数的部分走 TDD**（terminal_code 生成、后端患者对象→前端形状的归一化、上传 payload 组装、历史项映射）；**store/页面/网络/蓝牙 的接线只能真机+真后端手动验证**（HBuilderX 跑 `http://118.31.39.47`），与现有测试边界一致。
