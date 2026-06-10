# 首页足底压力热力图 + IMU 显示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 首页实时显示每个压力传感器的值（热力图着色 + 数字叠加，固定满量程 ADC 4093）和 IMU 原始数据（可折叠），步长换算成 cm。

**Architecture:** 纯前端展示。蓝牙 store 的 `realtime` 状态扩展出每脚 `pressure[9]` 与 `imu`；notify 回调每帧填充；首页 `home.vue` 把已有 9 个足图点位按 schema p1..p9 重排，按压力着色并叠数字，新增可折叠 IMU 卡。着色/换算逻辑抽成纯函数 `utils/footMetrics.js` 做 vitest。后端不动。

**Tech Stack:** uni-app + Vue3 (`<script setup>`) + Pinia；vitest（纯函数单测）。

参考 spec：`docs/superpowers/specs/2026-06-10-home-pressure-heatmap-imu-design.md`

---

## File Structure

| 文件 | 责任 | 改动 |
|---|---|---|
| `蓝牙uniapp/utils/footMetrics.js` | 纯函数：ADC→颜色着色、米→厘米换算 | 新建 |
| `蓝牙uniapp/tests/footMetrics.test.js` | footMetrics 单测 | 新建 |
| `蓝牙uniapp/store/modules/blueTooth.js` | `realtime` 加 `pressure[9]`+`imu`；notify 填充；断开复位 | 修改 |
| `蓝牙uniapp/pages/home/home.vue` | 点位 p1..p9 重排 + 热力着色 + 数字；IMU 折叠卡；步长 cm | 修改 |

约束（CLAUDE.md §3）：38 字段顺序以硬件为准，不得改解析顺序；注释只解释"为什么"。

---

## Task 1: 纯函数 footMetrics.js（着色 + 单位换算）

**Files:**
- Create: `蓝牙uniapp/utils/footMetrics.js`
- Test: `蓝牙uniapp/tests/footMetrics.test.js`

- [ ] **Step 1: 写失败测试**

`蓝牙uniapp/tests/footMetrics.test.js`：

```js
import { describe, it, expect } from 'vitest'
import { shade, mToCm, PMAX } from '../utils/footMetrics.js'

describe('PMAX', () => {
  it('满量程为 ADC 4093', () => {
    expect(PMAX).toBe(4093)
  })
})

describe('shade', () => {
  it('0（没踩）返回最浅蓝', () => {
    expect(shade(0)).toBe('rgb(219, 234, 254)')
  })
  it('满量程 4093 返回最深蓝', () => {
    expect(shade(4093)).toBe('rgb(29, 78, 216)')
  })
  it('超过满量程钳到最深', () => {
    expect(shade(9000)).toBe('rgb(29, 78, 216)')
  })
  it('非数值按 0 处理（最浅）', () => {
    expect(shade('abc')).toBe('rgb(219, 234, 254)')
    expect(shade(null)).toBe('rgb(219, 234, 254)')
  })
  it('中点附近线性插值', () => {
    // t ≈ 0.5 → 介于两端之间
    expect(shade(2046)).toBe('rgb(124, 156, 235)')
  })
})

describe('mToCm', () => {
  it('米换算厘米 ×100', () => {
    expect(mToCm(0.66)).toBeCloseTo(66, 5)
    expect(mToCm(1)).toBe(100)
  })
  it('非数值返回 NaN（供上层显示 -）', () => {
    expect(Number.isNaN(mToCm('-'))).toBe(true)
    expect(Number.isNaN(mToCm(null))).toBe(true)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd 蓝牙uniapp && npx vitest run tests/footMetrics.test.js`
Expected: FAIL（`Cannot find module '../utils/footMetrics.js'`）

- [ ] **Step 3: 写最小实现**

`蓝牙uniapp/utils/footMetrics.js`：

```js
// 足底压力/步态展示用纯函数（无副作用，便于 vitest）

// 压力传感器 ADC 满量程（0–4093，满量程≈10kg）。固定满量程使热力颜色跨帧/跨脚绝对可比。
export const PMAX = 4093

// 浅蓝 #dbeafe(219,234,254) → 深蓝 #1d4ed8(29,78,216)
const LOW = [219, 234, 254]
const HIGH = [29, 78, 216]

// 按 ADC 压力值返回热力颜色。非数值/缺失按 0（最浅）处理；超满量程钳到最深。
export function shade(adc) {
  const v = Number(adc)
  const t = Number.isFinite(v) ? Math.max(0, Math.min(1, v / PMAX)) : 0
  const c = LOW.map((lo, i) => Math.round(lo + (HIGH[i] - lo) * t))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

// 设备步长发的是米；显示用厘米。非数值返回 NaN（上层 fmt 会显示 '-'）。
export function mToCm(m) {
  const n = Number(m)
  return Number.isFinite(n) ? n * 100 : NaN
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd 蓝牙uniapp && npx vitest run tests/footMetrics.test.js`
Expected: PASS（全部用例通过）

> 注：中点用例 `shade(2046)`：t=2046/4093≈0.49988 → r=round(219+(29-219)*0.49988)=round(219-94.98)=124；g=round(234+(78-234)*0.49988)=round(234-77.98)=156；b=round(254+(216-254)*0.49988)=round(254-19.0)=235 → `rgb(124, 156, 235)`。

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/utils/footMetrics.js 蓝牙uniapp/tests/footMetrics.test.js
git commit -m "feat(app): footMetrics 纯函数（ADC 压力着色 + 米转厘米）"
```

---

## Task 2: 扩展蓝牙 store realtime 状态（pressure + imu）

**Files:**
- Modify: `蓝牙uniapp/store/modules/blueTooth.js`（`state` 里 `realtime` 初值 ~line 59；`disconnectDevice` 复位 ~line 200；连接回调掉线分支复位 ~line 388）

> 注意：文件里有 **3 处** 旧形状 `{ hasData: false, left: { speed:'-', length:'-', single:'-', double:'-' }, right: {...} }`——state 初值、`disconnectDevice`、connect 回调的「掉线/被断开」分支。三处都要换成 `emptyRealtime()`，否则形状不一致会让 Task 4 的 `pressure.map` 在复位后报错。

- [ ] **Step 1: 顶部新增工厂函数**

在文件顶部（import 之后、`defineStore`/`useBlueToothStore` 之前）新增：

```js
// realtime 初始空态（断开/未采集时）：压力全 0、IMU/参数为 '-'
function emptyRealtime() {
  const foot = () => ({
    pressure: [0, 0, 0, 0, 0, 0, 0, 0, 0],
    imu: { ax: '-', ay: '-', az: '-', gx: '-', gy: '-', gz: '-' },
    speed: '-', length: '-', single: '-', double: '-'
  })
  return { hasData: false, left: foot(), right: foot() }
}
```

- [ ] **Step 2: 改 state 初值（~line 59）**

把 `state` 里的：

```js
      realtime: {
        hasData: false,
        left: { speed: '-', length: '-', single: '-', double: '-' },
        right: { speed: '-', length: '-', single: '-', double: '-' }
      }
```

替换为：

```js
      realtime: emptyRealtime()
```

- [ ] **Step 3: 替换两处复位块（~line 200 与 ~line 388）**

两处完全相同的旧块：

```js
      this.realtime = {
        hasData: false,
        left: { speed: '-', length: '-', single: '-', double: '-' },
        right: { speed: '-', length: '-', single: '-', double: '-' }
      }
```

都替换为（注意保留各自原有缩进）：

```js
      this.realtime = emptyRealtime()
```

> 因两处文本相同，用编辑器「全部替换」或逐个定位 `disconnectDevice`（`ble.close()` 之后）与 connect 回调 `if (connected) { ... }` 分支两处。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp/store/modules/blueTooth.js
git commit -m "feat(app): realtime 状态扩展 pressure[9]+imu，复位用工厂函数"
```

---

## Task 3: notify 回调每帧填充 pressure + imu

**Files:**
- Modify: `蓝牙uniapp/store/modules/blueTooth.js`（notify 回调内更新 `this.realtime` 的那段，约在 `apiData` 构造之后）

- [ ] **Step 1: 替换 realtime 赋值块**

找到 notify 回调里现有的 `this.realtime = { hasData: true, left: { speed: apiData.left_speed, ... }, right: { ... } }` 整块，替换为同时带 `pressure`/`imu` 的版本（字段映射严格按已解析的 `apiData`）：

```js
              // 每帧刷新首页实时显示（与是否落库无关：即使未选患者也能看到数据）
              this.realtime = {
                hasData: true,
                left: {
                  pressure: [
                    apiData.lp1, apiData.lp2, apiData.lp3, apiData.lp4, apiData.lp5,
                    apiData.lp6, apiData.lp7, apiData.lp8, apiData.lp9
                  ],
                  imu: { ax: apiData.ax, ay: apiData.ay, az: apiData.az,
                         gx: apiData.gx, gy: apiData.gy, gz: apiData.gz },
                  speed: apiData.left_speed,
                  length: apiData.left_step_size,
                  single: apiData.left_single_sp_time,
                  double: apiData.left_double_sp_time
                },
                right: {
                  pressure: [
                    apiData.rp1, apiData.rp2, apiData.rp3, apiData.rp4, apiData.rp5,
                    apiData.rp6, apiData.rp7, apiData.rp8, apiData.rp9
                  ],
                  imu: { ax: apiData.right_ax, ay: apiData.right_ay, az: apiData.right_az,
                         gx: apiData.right_gx, gy: apiData.right_gy, gz: apiData.right_gz },
                  speed: apiData.right_speed,
                  length: apiData.right_step_size,
                  single: apiData.right_single_sp_time,
                  double: apiData.right_double_sp_time
                }
              }
```

> 说明：`apiData.lp1..lp9 / ax..gz / left_*` 与 `rp1..rp9 / right_ax..right_gz / right_*` 均已在上方 `apiData` 中由 `dataArray` 解析（下标顺序见 schema，勿改）。

- [ ] **Step 2: 静态核对（无单测，store 不便 mock）**

人工确认：左脚压力取 `lp1..lp9`、右脚取 `rp1..rp9`；左脚 IMU 取 `ax..gz`、右脚取 `right_ax..right_gz`。与 `apiData` 构造处字段名逐一对齐。

- [ ] **Step 3: 提交**

```bash
git add 蓝牙uniapp/store/modules/blueTooth.js
git commit -m "feat(app): notify 每帧填充左右脚 pressure[9]+imu 到 realtime"
```

---

## Task 4: 首页足图点位重排 + 热力着色 + 数字

**Files:**
- Modify: `蓝牙uniapp/pages/home/home.vue`（template 足图 + `<script setup>` + `.dot` 样式）

- [ ] **Step 1: 重排点位为 p1..p9**

把 `<script setup>` 里的 `pointsPercent` 整块替换为按 schema p1..p9 顺序（下标=传感器号，坐标沿用已调好的足图坐标）：

```js
// 点位（百分比坐标），下标 = 压力传感器编号 p1..p9（对应足底点位图 1–9）
// p1 脚趾 / p2 前掌内 / p3 前掌中 / p4 前掌外 / p5 足弓外 / p6 足弓内 / p7 中段 / p8 足跟上 / p9 足跟下
const pointsPercent = reactive({
  left: [
    { x: 37, y: 8 },
    { x: 37, y: 32 },
    { x: 29, y: 30 },
    { x: 22, y: 28 },
    { x: 34, y: 52 },
    { x: 18, y: 45 },
    { x: 34, y: 64 },
    { x: 29, y: 78 },
    { x: 29, y: 86 }
  ]
})
```

- [ ] **Step 2: 引入 footMetrics 并加着色/数值 computed**

在 `<script setup>` 顶部 import 区加：

```js
import { shade, mToCm } from '@/utils/footMetrics'
```

在 `rightPoints` computed 之后新增（着色始终算，数字仅在有数据时显示）：

```js
// 压力数值（整数）：无实时帧时显示空字符串，避免满屏 0
const leftVals = computed(() =>
  ble.realtime.hasData ? ble.realtime.left.pressure.map((v) => Math.round(Number(v) || 0)) : pointsPercent.left.map(() => ''))
const rightVals = computed(() =>
  ble.realtime.hasData ? ble.realtime.right.pressure.map((v) => Math.round(Number(v) || 0)) : pointsPercent.left.map(() => ''))
// 热力颜色（固定满量程 4093）
const leftColors = computed(() => ble.realtime.left.pressure.map(shade))
const rightColors = computed(() => ble.realtime.right.pressure.map(shade))
```

- [ ] **Step 3: 改步长换算为 cm**

把 `rt` computed 里左右脚 `length` 与平均 `length` 改为先 `mToCm` 再格式化：

```js
    left: { speed: fmt(r.left.speed), length: fmt(mToCm(r.left.length)), single: fmt(r.left.single), double: fmt(r.left.double) },
    right: { speed: fmt(r.right.speed), length: fmt(mToCm(r.right.length)), single: fmt(r.right.single), double: fmt(r.right.double) },
    avg: {
      speed: mean(r.left.speed, r.right.speed),
      length: mean(mToCm(r.left.length), mToCm(r.right.length)),
      leftSingle: mean(r.left.single, r.right.single),
      double: mean(r.left.double, r.right.double)
    }
```

> `mToCm` 非数值返回 `NaN`，`fmt`/`mean` 已把 `NaN` 显示成 `'-'`，无需额外判空。

- [ ] **Step 4: 模板足图绑定颜色与数字**

把 template 里两段 `v-for` 的 `.dot` 改为绑定动态背景并显示数字：

```html
      <!-- 左脚点位 -->
      <view v-for="(p, idx) in pointsPercent.left" :key="'l' + idx" class="dot"
        :style="{ left: p.x + '%', top: p.y + '%', background: leftColors[idx] }">{{ leftVals[idx] }}</view>
      <!-- 右脚点位（镜像） -->
      <view v-for="(p, idx) in rightPoints" :key="'r' + idx" class="dot"
        :style="{ left: p.x + '%', top: p.y + '%', background: rightColors[idx] }">{{ rightVals[idx] }}</view>
```

- [ ] **Step 5: 调整 `.dot` 样式（容纳数字、去掉 ripple 动画避免与数字打架）**

把 `<style>` 里 `.dot { ... }` 以及 `.dot::after,.dot::before { ... }`、`.dot::before { ... }`、`@keyframes ripple { ... }` 整段替换为：

```scss
.dot {
  position: absolute;
  width: 34rpx;
  height: 34rpx;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16rpx;
  font-weight: 700;
  color: #fff;
  /* 1px 白描边保证浅色背景上也看得清 */
  text-shadow: 0 0 2rpx rgba(0, 0, 0, 0.55);
  box-shadow: 0 0 0 4rpx rgba(96, 165, 250, 0.18);
}
```

- [ ] **Step 6: 真机/HBuilderX 自检**

无法 vitest（含 .vue）。人工：连接采集时按压传感器，对应点位变深、显示 ADC 整数；松开变浅；未连接/未采集时点位浅色无数字；步长显示为合理 cm（如 66），步速 m/s。

- [ ] **Step 7: 提交**

```bash
git add 蓝牙uniapp/pages/home/home.vue
git commit -m "feat(app): 首页足图按 p1..p9 重排+压力热力着色与数字，步长改 cm"
```

---

## Task 5: 首页 IMU 折叠卡

**Files:**
- Modify: `蓝牙uniapp/pages/home/home.vue`（template 在足图与「实时参数」之间插卡；`<script setup>` 加折叠状态与 IMU computed；样式）

- [ ] **Step 1: 加折叠状态与 IMU computed**

`<script setup>` 内（`hasData` computed 附近）新增：

```js
import { ref } from 'vue'  // 若已 import 则合并，勿重复

// IMU 折叠卡开关（默认折叠）
const imuOpen = ref(false)
// IMU 显示值：2 位小数；非数值显示 '-'
const imu = computed(() => {
  const f = (o) => ({
    ax: fmt(o.ax), ay: fmt(o.ay), az: fmt(o.az),
    gx: fmt(o.gx), gy: fmt(o.gy), gz: fmt(o.gz)
  })
  return { left: f(ble.realtime.left.imu), right: f(ble.realtime.right.imu) }
})
```

> `fmt` 是 home.vue 已有的格式化函数（2 位小数 / '-'）。`ref` 来自 `vue`——确认顶部 `import { reactive, computed } from 'vue'` 补上 `ref`。

- [ ] **Step 2: 模板插入 IMU 折叠卡**

在 template 里「实时参数」标题（`<view class="mh">实时参数</view>`）之前插入：

```html
    <view class="imu-card">
      <view class="imu-head" @tap="imuOpen = !imuOpen">
        <text>IMU 原始数据</text>
        <text class="imu-arrow">{{ imuOpen ? '▾' : '▸' }}</text>
      </view>
      <view v-if="imuOpen" class="imu-body">
        <view class="imu-col">
          <view class="imu-foot">左脚</view>
          <view class="imu-row">加速度 ax {{ imu.left.ax }} · ay {{ imu.left.ay }} · az {{ imu.left.az }}</view>
          <view class="imu-row">角速度 gx {{ imu.left.gx }} · gy {{ imu.left.gy }} · gz {{ imu.left.gz }}</view>
        </view>
        <view class="imu-col">
          <view class="imu-foot">右脚</view>
          <view class="imu-row">加速度 ax {{ imu.right.ax }} · ay {{ imu.right.ay }} · az {{ imu.right.az }}</view>
          <view class="imu-row">角速度 gx {{ imu.right.gx }} · gy {{ imu.right.gy }} · gz {{ imu.right.gz }}</view>
        </view>
      </view>
    </view>
```

- [ ] **Step 3: 加 IMU 卡样式**

在 `<style>` 末尾（`.mgrid` 之后）追加：

```scss
.imu-card { background: #fff; border-radius: 12rpx; margin: 24rpx 0 0; }
.imu-head { @include ca-font; display: flex; justify-content: space-between; align-items: center;
  padding: 22rpx 24rpx; font-size: 28rpx; font-weight: 700; color: $ca-t1; }
.imu-arrow { color: $ca-t3; font-size: 26rpx; }
.imu-body { display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; padding: 0 24rpx 22rpx; }
.imu-col { background: #f7f9fc; border-radius: 10rpx; padding: 16rpx; }
.imu-foot { font-size: 24rpx; font-weight: 700; color: $ca-t2; margin-bottom: 10rpx; }
.imu-row { font-size: 22rpx; color: $ca-t1; line-height: 1.7; }
```

- [ ] **Step 4: 真机/HBuilderX 自检**

人工：默认折叠仅见标题行；点一下展开见左右脚 6 轴读数（2 位小数）；采集中数值随帧变化；未采集时显示 '-'。

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/pages/home/home.vue
git commit -m "feat(app): 首页新增可折叠 IMU 原始数据卡"
```

---

## Task 6: 全量回归 + 文档更新

**Files:**
- Modify: `CLAUDE.md`、`系统架构方案.md`（记录进展，按 CLAUDE.md §3.3 要求）

- [ ] **Step 1: 跑全部纯函数单测**

Run: `cd 蓝牙uniapp && npm test`
Expected: PASS（原有 22 + footMetrics 用例全绿）

- [ ] **Step 2: 真机回归清单（HBuilderX → 真机）**

逐项确认：
- 连接鞋垫采集，足图 9 点随按压变色 + 显示 ADC 整数；松开变浅。
- 左右脚分别响应（左脚点位用 `lp*`、右脚用 `rp*`）。
- IMU 卡展开见左右脚 6 轴；az 接近重力量级可作"在动"佐证。
- 步长显示为 cm（合理量级），步速 m/s。
- 断开连接后足图恢复浅色、无数字，IMU/参数显示 '-'，不自动重连。

- [ ] **Step 3: 更新文档**

在 `CLAUDE.md` 第 2.1 节「已交付/待办」补一条：首页足底压力热力图（固定满量程 ADC 4093）+ 可折叠 IMU 实时显示已实现，步长显示改 cm；在 `系统架构方案.md` 对应阶段记录同样进展。

- [ ] **Step 4: 提交**

```bash
git add CLAUDE.md 系统架构方案.md
git commit -m "docs: 记录首页压力热力图+IMU 实时显示完成"
```

---

## Self-Review

- **Spec 覆盖**：①数据层扩展→Task 2/3；②足图热力+数字（方案 A，固定满量程 4093）→Task 4；③IMU 折叠卡→Task 5；④步长 cm/步速 m/s/格式化→Task 4 Step 3 + Task 1。全部覆盖。
- **Placeholder 扫描**：无 TBD/TODO；每个代码步骤含完整代码与期望输出。
- **类型/命名一致**：`shade`/`mToCm`/`PMAX`（Task1）在 Task4 import 一致；`emptyRealtime()`（Task2）在 state 初值 + 两处复位（共 3 处旧块）统一替换；`leftVals/rightVals/leftColors/rightColors`、`imuOpen`、`imu` 命名在模板与 script 间一致；`realtime.left/right.pressure` 数组形状（Task2 初值 9 元）与 Task3 填充 9 元、Task4 `.map` 一致。
- **数据完整性（CLAUDE.md §3.1）**：未改 38 字段解析顺序，仅读取既有 `apiData` 字段做展示。
