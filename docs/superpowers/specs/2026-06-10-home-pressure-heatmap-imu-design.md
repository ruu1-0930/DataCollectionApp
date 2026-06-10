# 首页实时「足底压力热力图 + IMU」显示 — 设计

日期：2026-06-10
分支：`feature/frontend-backend-alignment`
范围：采集端 App（`蓝牙uniapp/`），纯前端展示，不动后端与数据库。

## 背景与目标

设备每帧上报 38 个传感字段（前 19 左脚 / 后 19 右脚）。当前首页只显示步速/步长/单支撑/双支撑 4 项平均参数，**9 路压力与 6 轴 IMU 没有任何可视化**。本次让首页实时展示「每个压力传感器的值（热力图 + 数字）」与「IMU 原始数据」，便于采集时核对设备是否真在输出。

38 字段顺序（硬件固定，权威）：

| 序号 | 含义 | 序号 | 含义 |
|---|---|---|---|
| 1–9 | 左脚压力 p1..p9（对应足底点位图 1–9） | 20–28 | 右脚压力 p1..p9（与左脚对称） |
| 10–12 | 左脚加速度 ax, ay, az | 29–31 | 右脚加速度 ax, ay, az |
| 13–15 | 左脚角速度 gx, gy, gz | 32–34 | 右脚角速度 gx, gy, gz |
| 16 | 左脚步长 (m) | 35 | 右脚步长 (m) |
| 17 | 左脚步速 (m/s) | 36 | 右脚步速 (m/s) |
| 18 | 左脚单支撑时间 (s) | 37 | 右脚单支撑时间 (s) |
| 19 | 左脚双支撑时间 (s) | 38 | 右脚双支撑时间 (s) |

足底点位（左脚，右脚镜像）：1=脚趾，2/3/4=前掌（内→外），5/6=足弓（外/内），7=中段，8/9=足跟。

## 非目标（YAGNI）

- 不做历史热力回放、不做压力曲线趋势（数据页已有趋势）。
- 压力满量程已知（ADC 0–4093，满量程≈10kg），用固定满量程归一化（非每帧自适应），使颜色具备跨帧、跨脚的绝对可比性。
- 不改后端/数据库/上传链路。

## 设计

### 1. 数据层：扩展 `store/modules/blueTooth.js` 的 `realtime`

现状：`realtime.left/right` 仅 `{ speed, length, single, double }`。

改为每只脚补充 `pressure`（9 元数组）与 `imu`：

```js
realtime: {
  hasData: false,
  left:  { pressure: [0,0,0,0,0,0,0,0,0], imu: { ax:'-', ay:'-', az:'-', gx:'-', gy:'-', gz:'-' },
           speed:'-', length:'-', single:'-', double:'-' },
  right: { pressure: [0,0,0,0,0,0,0,0,0], imu: { ax:'-', ... }, speed:'-', length:'-', single:'-', double:'-' }
}
```

- notify 回调内已有解析后的 `apiData`（`lp1..lp9 / ax..gz / left_* ` 与 `rp1..rp9 / right_ax..right_gz / right_*`）。每帧填充：
  - `left.pressure = [apiData.lp1, ..., apiData.lp9]`，`right.pressure = [apiData.rp1, ..., apiData.rp9]`
  - `left.imu = { ax: apiData.ax, ay: apiData.ay, az: apiData.az, gx: apiData.gx, gy: apiData.gy, gz: apiData.gz }`
  - `right.imu = { ax: apiData.right_ax, ... right_gz }`
  - 步态字段维持现有映射不变。
- 与是否选患者/是否落库无关（即使未选患者也实时显示），与现有逻辑一致。
- `disconnectDevice` 复位 `realtime` 为初始空态（`hasData:false`、压力全 0、各值 `'-'`）。

### 2. 首页足图：热力图 + 数字叠加（方案 A）

`pages/home/home.vue`：

- **点位重排**：把 `pointsPercent.left` 按 schema p1..p9 顺序排列，使数组下标 = 传感器编号，直接绑定 `pressure[i]`。坐标按点位图：
  - p1 脚趾、p2/p3/p4 前掌（内→外）、p5/p6 足弓、p7 中段、p8/p9 足跟。
- 右脚 = 左脚位置镜像（`x → 100 - x`），右脚值取 `right.pressure[i]`。
- **每个点渲染**：
  - 颜色：按**固定满量程** `PMAX = 4093`（ADC 量程，≈10kg）归一化。`t = clamp(v / 4093, 0, 1)`；浅蓝（低）→ 深蓝（高）。没踩（v≈0）时浅色，踩满（接近 4093）时最深。固定满量程使颜色跨帧/跨脚绝对可比。
  - 数字：整数 ADC 压力值印在点上，字号约 9px + 1px 白色描边保证可读（前掌 2/3/4 点较密）。
- `realtime.hasData=false` 时，足图区域走原空态（或显示静态浅色点），不显示数字。
- 刷新节奏：每帧（约 5s）随 `realtime` 更新，瞬时值。

### 3. IMU 折叠卡

放在足图与「实时参数」网格之间：

- 默认**折叠**，仅一行标题「IMU 原始数据 ▸」，点击展开/收起（本地 `ref(false)` 状态）。
- 展开后两列：**左脚 / 右脚**；每列两行：`加速度 ax, ay, az`、`角速度 gx, gy, gz`，数值保留 2 位小数。
- 缺失/非数值显示 `-`。

### 4. 单位与格式

实时参数网格沿用现有 4 项与组件 `CaMetric`：

- 步速：`m/s`，2 位小数（不变）。
- 步长：设备发米 → **显示 ×100 cm**（1 位小数或整数）。注意现有 `home.vue` 已标 cm，但未做 ×100 换算——本次补上换算，确保数值正确。
- 单/双支撑：`s`，2 位小数（不变）。
- 压力：整数 ADC 值（0–4093）。着色满量程固定 `PMAX=4093`。
- 通用：任一值非数值/缺失显示 `-`；压力缺失按 0 着色。

## 受影响文件

| 文件 | 改动 |
|---|---|
| `蓝牙uniapp/store/modules/blueTooth.js` | `realtime` state 加 `pressure[9]` + `imu`；notify 回调每帧填充；断开复位 |
| `蓝牙uniapp/pages/home/home.vue` | 点位按 p1..p9 重排；热力着色 + 数字叠加；IMU 折叠卡；步长 ×100 换算 |

## 前后端联动

- **前端**：上述两文件。
- **后端**：无改动（38 字段解析/落库已实现，本次只是把已有字段画出来）。

## 测试与验收

- 纯函数（归一化着色 `shade(v, pmax)`、步长换算、格式化 `fmt`）可抽出加 vitest。
- 真机验收：连接鞋垫采集时，足图 9 点随按压变色 + 显示数字；IMU 卡展开见 6 轴读数；断开后归零走空态；步长显示为合理 cm 值；步速 m/s。
