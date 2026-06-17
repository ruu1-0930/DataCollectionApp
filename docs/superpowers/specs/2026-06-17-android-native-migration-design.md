# 步态采集 App 原生化设计方案（uni-app → Android 原生）

日期：2026-06-17
状态：设计已确认，待写实现计划

## 1. 背景与目标

现采集端 App 为 uni-app（Vue3 + Pinia + UTS 原生蓝牙），用 HBuilderX 云打包。问题：

1. HBuilderX 云打包标准基座**带开屏广告**。
2. 团队希望后续在 **Android Studio** 里开发调试。

**决策**：完整重写为 **Android 原生（Kotlin + Jetpack Compose）App**，与现有 `蓝牙uniapp/` 并列存放、旧工程保留作对照。选原生重写而非 uni-app 离线打包的理由：仓库已含底层开源原生蓝牙源码（`com/clj/fastble`）可逐行对照，准确性高；且彻底脱离 DCloud/付费加密插件依赖，长期可维护性最好。

**范围边界**：

- 后端 `back/`（Flask + RDS + SVM）**零改动**；采集协议、数据模型不动；不加新功能。
- 1:1 复刻现有 7 个真实屏幕与临床流程；丢弃遗留开发页。
- 只做 Android；不做 iOS/鸿蒙。

## 2. 位置与环境（隔离，复用已装 SDK / Android Studio）

- 新目录：`DataCollectionApp/android-native/`，与 `蓝牙uniapp/` 并列。旧工程原样保留，不动。
- **Gradle wrapper**：项目内 `gradlew`，Gradle 自动下载到项目 `.gradle/`，不依赖系统 Gradle。
- **JDK**：固定为 Android Studio 自带 JBR 21（已验证 `D:\Program Files (x86)\Android Studio\jbr` = OpenJDK 21.0.10）。在 `gradle.properties` 设 `org.gradle.java.home`。不污染系统 `JAVA_HOME`/PATH。
- **Android SDK**：复用已安装的 `C:\Users\Lenovo\AppData\Local\Android\Sdk`（已有 platform android-36、build-tools 36/37、platform-tools/adb）。通过 `local.properties` 的 `sdk.dir` 引用；`local.properties` 机器本地、加入 `.gitignore`。
- 构建/识别参数：
  - 语言 Kotlin；UI 用 Jetpack Compose。
  - `compileSdk=36`、`targetSdk=36`（本机仅装了 android-36 平台）、`minSdk=26`（Android 8，覆盖约 98%，现代且稳妥）。
  - `applicationId=com.sarcopenianus.collector`、`namespace` 同名。
  - 应用显示名：步态采集。
  - ABI：`arm64-v8a`、`armeabi-v7a`（去掉 x86，与现状一致）。
  - AGP + Gradle 版本：按 JBR21 + compileSdk36 选稳定组合，具体版本号在实现计划阶段确定。

## 3. 整体架构（MVVM + 单向数据流）

对应现有 Pinia→Vue 的响应式模型：

```
UI 层      Compose 屏幕 + 组件         （对应 pages/ + components/Ca*）
   ↑ StateFlow              ↓ 事件
ViewModel  OperatorVM / PatientVM / BleVM   （对应 store/modules/*）
   ↑                         ↓
Repository Clinician/Patient/Device + Ble 编排
   ↓             ↓
Network(Retrofit)   BLE(vendored fastble)   Local(DataStore)
```

模块边界与对照：

| 原 uni-app | 新原生 | 职责 |
|---|---|---|
| `store/modules/operator.js` | `OperatorViewModel` + `OperatorRepository` | 启用/解锁/换 token/资料 |
| `store/modules/patient.js` | `PatientViewModel` + `PatientRepository` | 患者列表/新建/选择/历史 |
| `store/modules/blueTooth.js` | `BleViewModel` + `BleRepository` | 扫描/连接/采集/上传编排 |
| `utils/request.js` | OkHttp 拦截器 + Retrofit | token 注入 + 401 静默重试 |
| `utils/apiShape.js` | 纯 Kotlin 映射函数 | 后端↔前端形状映射 |
| `utils/footMetrics.js` | 纯 Kotlin 函数 | 热力着色 / 单位换算 |
| `utils/terminal.js` | 纯 Kotlin 函数 + DataStore | terminal_code 生成/持久化 |
| `utils/patient.js` | 纯 Kotlin 函数 | 患者搜索/排序 |
| `utils/clinicStorage.js`/`auth.js` | DataStore | 本地持久化 |

每个单元目标：职责单一、接口清晰、可独立理解与测试。纯逻辑与 BLE/网络/UI 副作用分离。

## 4. 蓝牙模块（最高保真，照搬现有原生栈）

- 把仓库 `蓝牙uniapp/uni_modules/android-ble/utssdk/app-android/com/clj/fastble/**` 的 Java 源码**原样 vendored** 进新工程（连同 `ByteUtil.java`、`HexUtil.java` 等），Kotlin 直接调用 `BleManager`。**丢弃付费加密 UTS 壳 `index.uts`/`BleHelper.kt`**——只取开源底层引擎。
- 将 `blueTooth.js` 的编排逻辑 1:1 译为 Kotlin：
  - **扫描**：按 MAC 去重、过滤无名设备、标记是否已在设备列表（对应 `scanNearbyDevices`）。
  - **运行时权限**：Android 12+（API 31）申请 `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`；旧版扫描申请 `ACCESS_FINE_LOCATION`（对应 `requestBlePermissions`）。
  - **连接**：`autoConnect=false`；首连 GATT133 等失败**自动重试一次**；已连后掉线/手动断开**只复位状态、绝不自动重连**（对应 `connectDevice` 的 `connected`/`retriesLeft` 逻辑）。
  - **服务发现**：自定义服务固定取 `services[2]`；写特征 = 含 `WRITE` 属性者，通知特征 = 含 `NOTIFY` 属性者（如 `4f93ccac`）。
  - **MTU**：`setMtu(512)`。
  - **数据解析**：NOTIFY 字节流 → 字符串 → 按 `,` split → 去 `\n`；**长度必须 = 38，否则整帧丢弃**；按固定顺序映射为左脚 19（p1..p9 + 6 IMU + 步长/步速/单支撑/双支撑）+ 右脚 19。
  - **写指令**：`toHex` 后 `writeStringDataToBle`（仅当设备暴露可写特征；当前鞋垫只有 NOTIFY，通常不下发）。
- 协议常量与 38 字段解析抽成独立纯类 `InsoleFrameParser`，便于 JUnit 单测（不接触蓝牙硬件）。

## 5. 网络层与后端契约（后端零改动）

- 技术：Retrofit + OkHttp + kotlinx-serialization。baseURL `https://api.sarcopenianus.com`，强制 HTTPS、校验证书（对齐 `sslVerify:true`，不得关闭）。
- 接口（路径/方法/字段保持现状）：
  - 医护：`POST /clinician/enable`、`POST /clinician/login`、`GET /clinician/me`、`PUT /clinician/me`
  - 患者：`GET /patients`、`POST /patients`、`GET /patients/{id}`、`GET /patients/{id}/data`（params: start/end/page/page_size）
  - 设备：`GET /devices`、`POST /devices`、`DELETE /devices/{id}`、`POST /devices/{device_code}/raw_data`（body: `patient_id` + 38 命名字段）
- 响应约定：成功体形如 `{ code/status, msg, data }`，取 `data`；非 200 提示 `msg`。
- **Token**：enable/login 返回 `token`，本地存为 `Bearer xxx` 整串。OkHttp 请求拦截器加 `Authorization`；无 token 时仅放行 enable/login，其余请求静默取消（不强制登出）。
- **401 静默重试一次**：用本地 `phone + terminal_code + passcode` 调 `/clinician/login` 换新 token 后重放原请求一次；重试请求打标记防无限循环；enable/login 自身不参与重试；失败提示「鉴权失败，请重新解锁」不弹登录页、不清本地数据（对齐 `retryWithRefresh`）。
- **terminal_code**：v4-UUID 形状字符串，首次生成并持久化（换机/重装视为新终端，可接受）。

## 6. 状态与本地持久化

- **DataStore(Preferences)** 取代 `uni.storage`，键语义沿用：
  - operator 档案：`{ hospital, dept, name, phone, passcode, enabled, clinicianId, terminalCode }`
  - patients 本地缓存（离线展示）、currentPatientId（后端 patient_id）
  - token、terminalCode
- `unlocked` 为**内存态、不持久化**：每次冷启动都需重新解锁（与现状一致）。
- 患者列表权威以后端为准（`loadList` 拉取后写缓存）；本地缓存用于离线展示与按 `lastAt` 倒序 + 关键字过滤。

## 7. 屏幕与导航（7 屏，1:1）

- **启动网关**（对应 `App.vue onLaunch`，用单 Activity + Compose Navigation 起始路由决策）：
  1. 未启用 → `enable`
  2. 已启用、未解锁 → `unlock`
  3. 已解锁、无当前患者 → `patient/select`
  4. 已启用 + 已解锁 + 有当前患者 → 首页
- **底部 3 Tab**：首页（home）/ 数据（data）/ 我的（mine）。
- **普通页面**：`setup/enable`（医院/科室/医生/手机 + 自设口令，启用）、`setup/unlock`（口令解锁）、`patient/select`（选患者 + 搜索）、`patient/new`（新建患者，含查重命中提示）。
- 屏幕职责：
  - **首页**：当前患者条；蓝牙开关/连接态；连接后实时足底压力热力图 + IMU 卡 + 步态参数；未选患者可看实时但禁止上传。
  - **数据**：按当前患者拉 `/patients/{id}/data` 历史（每脚 L/R 一行，含压力/IMU/步态 + SVM T 值），可视化展示。
  - **我的**：操作员资料（查看/编辑 `/clinician/me`）+ 设备管理（蓝牙搜索附近设备添加、列表、删除）。
- **丢弃遗留页**：`index/index`（旧蓝牙测试页）、`test/read`、`test/write`。

## 8. 实时可视化（首页足底热力图 + IMU）

- Compose `Canvas` 画足底 9 点热力图：
  - 底图沿用 `foot.png`（从旧工程 `static/` 复制资源）。
  - 9 个点位坐标按硬件 schema `p1..p9` 排布，**坐标从旧 `home.vue` 精确移植**。
  - 着色 `shade(adc)`：PMAX=4093 固定满量程，浅蓝 `#dbeafe(219,234,254)` → 深蓝 `#1d4ed8(29,78,216)` 线性插值；非数值/缺失按 0、超量程钳到最深。颜色跨帧/跨脚绝对可比。
  - ADC 整数值叠在点上。
- 可折叠「IMU 原始数据」卡：左右脚各加速度/角速度 6 轴，2 位小数。
- 步态参数：步长 `mToCm`（×100，显示 cm）、步速 m/s、单/双支撑。
- 数据源：`BleViewModel.realtime` StateFlow；断开/未采集时归零空态。

## 9. 测试

- **JUnit 纯逻辑单测**（以现有 vitest 用例为对照基准）：
  - `shade` / `mToCm`（footMetrics）
  - 38 字段 CSV 解析（InsoleFrameParser）
  - payload/形状映射（`buildRawDataPayload` / `mapHistoryItem` / `normalizePatient`）
  - terminal_code 形状（注入 rng）
  - 患者搜索/排序（patient）
- **真机手动回归**（蓝牙与 Compose UI 无法离机单测）：沿用旧工程真机清单——启用本机、选/建患者、连接鞋垫、采集上传落库 + 归属、按患者查历史、断开归零。

## 10. 风险与缓解

1. **38 字段顺序硬编码**：以硬件文档为准，与旧 `blueTooth.js` 解析逐字段对照；改解析前与硬件团队核对。
2. **真机 GATT 行为**：连接重试/MTU/notify 需现场真机验证，不能仅靠单测。
3. **foot.png 点位坐标**：必须从旧 `home.vue` 精确移植，否则热力点错位。
4. **AGP/Gradle/Compose 版本组合**：需选与 JBR21 + compileSdk36 兼容的稳定组合，计划阶段锁定。
5. **付费加密插件**：仅取开源 fastble 底层，不碰加密 UTS 壳，规避授权问题。

## 11. 不在本次范围

- 后端、数据库、采集协议改动。
- iOS / 鸿蒙。
- 任何新功能或 UI 重设计（严格 1:1 复刻现有行为与视觉）。
- 批量上传/离线重传（属架构方案阶段 2，另立计划）。
