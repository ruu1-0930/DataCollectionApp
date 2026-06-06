# 采集端 App 前端改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `蓝牙uniapp/` 采集端 App 从「个人 App」界面，改造成「医护操作员 + 患者档案」的临床多患者界面，并统一视觉风格、修掉 `0.000000`/`-` 占位。

**Architecture:** 新增两个 Pinia 模块（operatorStore = 设备启用档案+口令；patientStore = 当前患者+患者列表），用本地存储持久化；App 启动时按「已启用?→已解锁?→已选患者?」逐级网关跳转。视觉层抽出 SCSS design tokens + 6 个可复用组件，逐页套用。真实数据接入与后端表改造**不在本计划**，数据层先用本地 mock + 空态占位。

**Tech Stack:** uni-app (Vue3 `<script setup>`) + Pinia + SCSS（`uni.scss`）+ qiun-data-charts(uCharts) + 现有 UTS `android-ble` 插件（不动）。

---

## 阅读须知（实现者必看）

### 项目现状关键事实
- **构建方式**：HBuilderX 编译到 Android 真机。蓝牙原生模块需真机/自定义基座，**纯逻辑可在 H5 预览快速验证**。
- **无测试框架**：`package.json` 为空，项目靠 HBuilder 管理，无 npm 测试链路。
- **无 git 仓库**：`D:\ME5001` 未初始化 git。若要按任务提交 checkpoint，先在仓库根 `git init`；否则忽略各任务的 `commit` 步骤（它们是可选的进度锚点）。
- **Pinia 入口**：`store/index.js` 导出 `store`、`setupStore`；模块用 `defineStore` + `useXxxStoreWithOut()` 包装（见 `store/modules/user.js`）。**注意**：`main.js` 当前未调用 `setupStore(app)`，但各 store 通过 `useXxxStore(store)` 传入 pinia 实例，故能用。新建 store 照抄 `user.js` 的 `useXxxStoreWithOut` 写法即可。
- **持久化范式**：用 `uni.getStorageSync/setStorageSync`，封装在独立文件里（范式见 `utils/auth.js`）。
- **路由**：`pages.json` 的 `pages` 数组第一项是默认首页（当前 `pages/home/home`）；tabBar 有 首页/数据/我的。非 tab 页用 `uni.navigateTo/redirectTo`，tab 页用 `uni.switchTab`。
- **图表**：`utils/ucharts.js` 暴露 `getRingOpts`/`getBarOpts`；`qiun-data-charts` 为全局 easycom 组件。
- **蓝牙 store**（`store/modules/blueTooth.js`）现有 actions：`getDevicesList()`、`connectDevice(id)`、`disconnectDevice(id)`、`addDevice(deviceStr)`、`deleteDevice(id)`、`updateDevice(id,data)`、`searchDevice()`、`initBle()`；state 有 `deviceList`、`isBluetoothOpen`。**本计划不改蓝牙协议/解析逻辑**，只复用这些 action 并重做 UI。

### 设计来源（视觉唯一事实源）
已确认的高保真预览在 `D:\ME5001\.superpowers\brainstorm\1177-1780745422\content\`：
`design-tokens.html`、`components.html`、`page-setup-patient.html`、`page-device-v4.html`、`page-home-v3.html`、`page-data.html`。
**实现页面时对照这些文件还原布局/间距/配色**。spec 见 `docs/superpowers/specs/2026-06-06-frontend-redesign-design.md`。

### 测试方式（重要 —— 本计划的纪律点）
这是 uni-app 可视化改版 + 原生蓝牙 + 后端未接，**没有可自动化的页面渲染测试面**。因此：
- **纯逻辑（`utils/patient.js`：编号格式化、手机号脱敏、搜索过滤、字段校验）→ 真单元测试**（Task 2 搭最小 vitest）。这是最容易藏 bug 的地方，必须测。
- **Store / 页面 / 组件 → 人工验收**：每个任务给出明确的「验收标准」（在 HBuilderX H5 预览或真机上逐条核对）。这是有意为之，不是偷懒：可视化与原生交互在此栈下只能人工核验。

每个任务的「验证」步骤要么是「跑单测」要么是「按验收清单在预览里核对」。

### rpx 约定
预览是 px（375 宽手机）。uni-app 页面用 **rpx**（750 = 屏宽），换算 `rpx ≈ px × 2`。tokens 里的颜色直接用 px/十六进制不变；尺寸按需换 rpx。

---

## 文件结构（先锁定边界）

**新建：**
- `蓝牙uniapp/styles/tokens.scss` — design tokens（颜色/圆角/阴影/字体 mixin）
- `蓝牙uniapp/utils/patient.js` — 纯逻辑：编号生成/格式化、手机号脱敏、搜索过滤、校验（无 `uni.*` 依赖）
- `蓝牙uniapp/utils/clinicStorage.js` — 操作员档案 + 患者列表 + 当前患者 的本地存储读写（仿 `auth.js`）
- `蓝牙uniapp/store/modules/operator.js` — operatorStore（启用档案、口令、锁状态）
- `蓝牙uniapp/store/modules/patient.js` — patientStore（患者列表、当前患者、增/查/选）
- `蓝牙uniapp/components/base/CaInput.vue` — 统一输入框
- `蓝牙uniapp/components/base/CaCard.vue` — 卡片容器
- `蓝牙uniapp/components/base/CaMetric.vue` — 指标卡（标题/数值/单位/左右）
- `蓝牙uniapp/components/base/CaStatusStrip.vue` — 采集中状态条
- `蓝牙uniapp/components/base/CaEmpty.vue` — 空态
- `蓝牙uniapp/components/base/CaPatientBar.vue` — 当前患者条
- `蓝牙uniapp/pages/setup/enable.vue` — 首次启用
- `蓝牙uniapp/pages/setup/unlock.vue` — 解锁
- `蓝牙uniapp/pages/patient/select.vue` — 患者选择
- `蓝牙uniapp/pages/patient/new.vue` — 新建患者
- `蓝牙uniapp/tests/patient.test.js` — patient.js 单测
- `蓝牙uniapp/vitest.config.js`、`package.json`（测试脚本）— 最小测试环境

**修改：**
- `蓝牙uniapp/uni.scss` — 引入 tokens
- `蓝牙uniapp/store/modules/index.js` — 导出新 store（确认现有导出方式后追加）
- `蓝牙uniapp/App.vue` — onLaunch 启动网关
- `蓝牙uniapp/pages.json` — 增删页面、首页指向网关
- `蓝牙uniapp/pages/home/home.vue` — 重做实时参数（足底区**保持原样**）
- `蓝牙uniapp/pages/data/data.vue` — 重做为「时间分段 + KPI + 折线/柱 + 空态」
- `蓝牙uniapp/pages/mine/mine.vue` — 设备连接&采集 + 我的精简 + 操作员资料 + 重新启用

**删除（最后清理）：**
- `蓝牙uniapp/pages/login/login.vue`、`蓝牙uniapp/pages/register/register.vue`
- `pages/data/data copy.vue`、`pages/home/home copy.vue`（死文件）
- 登录页对 `utils/networkDiagnostic.js` 的暴露调用

---

## Phase 0 — 基础设施（tokens / 逻辑 / store / 组件）

### Task 1: Design tokens（SCSS 变量）

**Files:**
- Create: `蓝牙uniapp/styles/tokens.scss`
- Modify: `蓝牙uniapp/uni.scss`

- [ ] **Step 1: 写 tokens.scss**

```scss
// styles/tokens.scss —— 临床浅色主题 design tokens
// 与 .superpowers 预览 design-tokens.html 对齐
$ca-primary:        #2F6DF6;
$ca-primary-light:  #E7F0FE;
$ca-success:        #15A05A; // 右脚/正向
$ca-warning:        #E8A33D; // 采集中
$ca-danger:         #E5484D; // 停止/必填/下降
$ca-bg:             #F5F7FA;
$ca-border:         #E6EBF2;
$ca-t1:             #0F172A; // 主文字
$ca-t2:             #64748B; // 次文字
$ca-t3:             #94A3B8; // 弱文字

$ca-radius-card:    28rpx; // ~14px
$ca-radius-input:   24rpx; // ~12px
$ca-shadow-card:    0 2rpx 6rpx rgba(16, 42, 80, 0.06);

// 字体：Inter / PingFang SC（不用 Segoe UI / 等宽）
@mixin ca-font {
  font-family: 'Inter', 'PingFang SC', -apple-system, sans-serif;
}
```

- [ ] **Step 2: 在 uni.scss 末尾引入 tokens**

在 `蓝牙uniapp/uni.scss` 文件**最后**追加：

```scss
/* 临床浅色主题 tokens（本次改版新增） */
@import "@/styles/tokens.scss";
```

- [ ] **Step 3: 验证**

在 HBuilderX 运行到 H5。新建任一组件用 `color: $ca-primary;` 不报 SCSS 编译错即通过。（无独立单测，编译通过即验收。）

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/styles/tokens.scss 蓝牙uniapp/uni.scss
git commit -m "feat(ui): add clinical light design tokens"
```

---

### Task 2: 纯逻辑 utils/patient.js + 单测环境

**Files:**
- Create: `蓝牙uniapp/utils/patient.js`
- Create: `蓝牙uniapp/tests/patient.test.js`
- Create: `蓝牙uniapp/vitest.config.js`
- Create/Modify: `蓝牙uniapp/package.json`

- [ ] **Step 1: 写 utils/patient.js（无 uni.* 依赖，纯函数）**

```js
// utils/patient.js —— 患者相关纯逻辑，可单测
// 编号方案：系统自动假名 subject_id，格式 #00001（5 位补零）
export function formatSubjectId(seq) {
  const n = Math.max(0, Math.floor(Number(seq) || 0))
  return '#' + String(n).padStart(5, '0')
}

// 根据已有最大序号生成下一个序号
export function nextSeq(patients) {
  const max = (patients || []).reduce((m, p) => Math.max(m, p.seq || 0), 0)
  return max + 1
}

// 手机号脱敏：138****6543（非 11 位原样返回）
export function maskPhone(phone) {
  const s = String(phone || '').replace(/\s/g, '')
  if (s.length !== 11) return s
  return s.slice(0, 3) + '****' + s.slice(7)
}

// 11 位手机号校验
export function isValidPhone(phone) {
  return /^1\d{10}$/.test(String(phone || '').trim())
}

// 新建患者字段校验，返回 { ok, msg }
export function validatePatient({ name, phone } = {}) {
  if (!name || !String(name).trim()) return { ok: false, msg: '请输入患者姓名' }
  if (!isValidPhone(phone)) return { ok: false, msg: '请输入正确的 11 位手机号' }
  return { ok: true, msg: '' }
}

// 搜索：按 姓名 / 手机号 / 编号(数字或#) 匹配，返回过滤后的列表
export function searchPatients(patients, keyword) {
  const k = String(keyword || '').trim().toLowerCase()
  if (!k) return patients || []
  const kDigits = k.replace(/[^0-9]/g, '')
  return (patients || []).filter((p) => {
    const name = String(p.name || '').toLowerCase()
    const phone = String(p.phone || '')
    const id = formatSubjectId(p.seq).toLowerCase() // 形如 #00001
    if (name.includes(k)) return true
    if (kDigits && phone.includes(kDigits)) return true
    if (id.includes(k)) return true
    if (kDigits && String(p.seq).includes(kDigits)) return true
    return false
  })
}
```

- [ ] **Step 2: 写最小测试环境**

`蓝牙uniapp/package.json`（若已存在则只合并 `scripts`/`devDependencies`）:

```json
{
  "name": "bluetooth-uniapp",
  "private": true,
  "scripts": {
    "test": "vitest run"
  },
  "devDependencies": {
    "vitest": "^1.6.0"
  }
}
```

`蓝牙uniapp/vitest.config.js`:

```js
import { defineConfig } from 'vitest/config'
export default defineConfig({
  test: { environment: 'node', include: ['tests/**/*.test.js'] }
})
```

- [ ] **Step 3: 写失败的单测**

`蓝牙uniapp/tests/patient.test.js`:

```js
import { describe, it, expect } from 'vitest'
import {
  formatSubjectId, nextSeq, maskPhone, isValidPhone, validatePatient, searchPatients
} from '../utils/patient.js'

describe('formatSubjectId', () => {
  it('补零到 5 位并带 #', () => {
    expect(formatSubjectId(427)).toBe('#00427')
    expect(formatSubjectId(1)).toBe('#00001')
  })
})

describe('nextSeq', () => {
  it('返回最大 seq + 1', () => {
    expect(nextSeq([{ seq: 3 }, { seq: 7 }, { seq: 5 }])).toBe(8)
    expect(nextSeq([])).toBe(1)
  })
})

describe('maskPhone', () => {
  it('脱敏中间四位', () => {
    expect(maskPhone('13812346543')).toBe('138****6543')
  })
  it('非 11 位原样返回', () => {
    expect(maskPhone('123')).toBe('123')
  })
})

describe('isValidPhone', () => {
  it('11 位 1 开头为真', () => {
    expect(isValidPhone('13812346543')).toBe(true)
    expect(isValidPhone('2381234654')).toBe(false)
    expect(isValidPhone('138123465')).toBe(false)
  })
})

describe('validatePatient', () => {
  it('缺姓名报错', () => {
    expect(validatePatient({ name: '', phone: '13812346543' }).ok).toBe(false)
  })
  it('手机号非法报错', () => {
    expect(validatePatient({ name: '张三', phone: '123' }).ok).toBe(false)
  })
  it('合法通过', () => {
    expect(validatePatient({ name: '张三', phone: '13812346543' }).ok).toBe(true)
  })
})

describe('searchPatients', () => {
  const list = [
    { seq: 427, name: '张建国', phone: '13812346543' },
    { seq: 408, name: '张建国', phone: '15912342071' },
    { seq: 426, name: '王秀兰', phone: '13612348890' }
  ]
  it('空关键字返回全部', () => {
    expect(searchPatients(list, '').length).toBe(3)
  })
  it('按姓名命中同名两条', () => {
    expect(searchPatients(list, '张建国').length).toBe(2)
  })
  it('按手机号区分同名', () => {
    const r = searchPatients(list, '1591234')
    expect(r.length).toBe(1)
    expect(r[0].seq).toBe(408)
  })
  it('按编号命中', () => {
    expect(searchPatients(list, '#00426')[0].name).toBe('王秀兰')
    expect(searchPatients(list, '427')[0].name).toBe('张建国')
  })
})
```

- [ ] **Step 4: 跑测试，先确认能跑（红或绿）**

Run（在 `蓝牙uniapp/` 下）: `npm install && npm test`
Expected: 若 patient.js 已按 Step 1 写好 → 全 PASS；若环境无 npm，则跳过本任务的自动化，改在 HBuilder H5 控制台手动 `import` 调用核对上述用例。

- [ ] **Step 5: 让测试全绿**

如有 FAIL，对照断言修 `utils/patient.js`，重跑 `npm test` 至全 PASS。

- [ ] **Step 6: Commit（可选）**

```bash
git add 蓝牙uniapp/utils/patient.js 蓝牙uniapp/tests/patient.test.js 蓝牙uniapp/vitest.config.js 蓝牙uniapp/package.json
git commit -m "feat(patient): add patient pure logic with unit tests"
```

---

### Task 3: 本地存储封装 utils/clinicStorage.js

**Files:**
- Create: `蓝牙uniapp/utils/clinicStorage.js`

- [ ] **Step 1: 写存储封装（仿 utils/auth.js）**

```js
// utils/clinicStorage.js —— 操作员档案 / 患者列表 / 当前患者 的本地持久化
const OPERATOR_KEY = '__operator__'   // { hospital, dept, name, phone, passcode, enabled }
const PATIENTS_KEY = '__patients__'   // [ { seq, name, phone, gender, age, createdAt, lastAt, count } ]
const CURRENT_KEY  = '__current_patient__' // seq

export function getOperator() {
  try { return uni.getStorageSync(OPERATOR_KEY) || null } catch (e) { return null }
}
export function setOperator(op) { uni.setStorageSync(OPERATOR_KEY, op) }
export function clearOperator() { uni.removeStorageSync(OPERATOR_KEY) }

export function getPatients() {
  try { return uni.getStorageSync(PATIENTS_KEY) || [] } catch (e) { return [] }
}
export function setPatients(list) { uni.setStorageSync(PATIENTS_KEY, list || []) }

export function getCurrentSeq() {
  try { return uni.getStorageSync(CURRENT_KEY) || null } catch (e) { return null }
}
export function setCurrentSeq(seq) { uni.setStorageSync(CURRENT_KEY, seq) }
export function clearCurrentSeq() { uni.removeStorageSync(CURRENT_KEY) }
```

- [ ] **Step 2: 验证**

HBuilder H5 控制台 `import('@/utils/clinicStorage.js')` 后调用 `setPatients([{seq:1}])` 再 `getPatients()` 应返回该数组。验收：读写一致、无报错。

- [ ] **Step 3: Commit（可选）**

```bash
git add 蓝牙uniapp/utils/clinicStorage.js
git commit -m "feat(storage): add clinic local storage helpers"
```

---

### Task 4: operatorStore（设备启用 + 口令 + 锁）

**Files:**
- Create: `蓝牙uniapp/store/modules/operator.js`
- Modify: `蓝牙uniapp/store/modules/index.js`

- [ ] **Step 1: 确认现有模块导出方式**

Read `蓝牙uniapp/store/modules/index.js`，照其现有 `export * from './xxx'` 风格在末尾追加导出（下一步）。

- [ ] **Step 2: 写 operator.js**

```js
import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'

export const useOperatorStore = defineStore('operatorStore', {
  state: () => ({
    operator: getOperator() || null, // { hospital, dept, name, phone, passcode, enabled }
    unlocked: false                  // 本次启动是否已解锁（不持久化）
  }),
  getters: {
    isEnabled: (s) => !!(s.operator && s.operator.enabled)
  },
  actions: {
    // 首次启用：保存档案 + 口令，并视为已解锁
    enable({ hospital, dept, name, phone, passcode }) {
      this.operator = { hospital, dept, name, phone, passcode, enabled: true }
      setOperator(this.operator)
      this.unlocked = true
    },
    // 解锁校验
    unlock(passcode) {
      if (this.operator && passcode === this.operator.passcode) {
        this.unlocked = true
        return true
      }
      return false
    },
    // 重新启用本机（清档案，回到启用页）
    reset() {
      this.operator = null
      this.unlocked = false
      clearOperator()
    },
    // 采集归属信息（写入采集数据用）
    attribution() {
      const o = this.operator || {}
      return { hospital: o.hospital, dept: o.dept, doctor: o.name }
    }
  }
})

export function useOperatorStoreWithOut() {
  return useOperatorStore(store)
}
```

- [ ] **Step 3: 追加导出**

在 `store/modules/index.js` 末尾按现有风格追加：

```js
export * from './operator'
```

- [ ] **Step 4: 验证**

H5 预览，控制台调用 `useOperatorStoreWithOut().enable({hospital:'A',dept:'B',name:'李',phone:'13812346543',passcode:'1234'})`，再 `isEnabled` 为 `true`、`unlock('1234')` 返回 `true`、`unlock('x')` 返回 `false`、`reset()` 后 `isEnabled` 为 `false`。逐条核对。

- [ ] **Step 5: Commit（可选）**

```bash
git add 蓝牙uniapp/store/modules/operator.js 蓝牙uniapp/store/modules/index.js
git commit -m "feat(store): add operator store (device enablement + passcode)"
```

---

### Task 5: patientStore（患者列表 + 当前患者）

**Files:**
- Create: `蓝牙uniapp/store/modules/patient.js`
- Modify: `蓝牙uniapp/store/modules/index.js`

- [ ] **Step 1: 写 patient.js**

```js
import { defineStore } from 'pinia'
import { store } from '@/store'
import { getPatients, setPatients, getCurrentSeq, setCurrentSeq, clearCurrentSeq } from '@/utils/clinicStorage'
import { nextSeq, formatSubjectId, searchPatients } from '@/utils/patient'

export const usePatientStore = defineStore('patientStore', {
  state: () => ({
    patients: getPatients() || [],
    currentSeq: getCurrentSeq() || null
  }),
  getters: {
    current: (s) => s.patients.find((p) => p.seq === s.currentSeq) || null,
    currentId: (s) => {
      const p = s.patients.find((x) => x.seq === s.currentSeq)
      return p ? formatSubjectId(p.seq) : ''
    }
  },
  actions: {
    // 新建患者并设为当前，返回新患者
    create({ name, phone, gender, age }) {
      const seq = nextSeq(this.patients)
      const now = Date.now()
      const p = { seq, name, phone, gender: gender || '', age: age || '', createdAt: now, lastAt: now, count: 0 }
      this.patients = [p, ...this.patients]
      setPatients(this.patients)
      this.select(seq)
      return p
    },
    select(seq) {
      this.currentSeq = seq
      setCurrentSeq(seq)
    },
    clearCurrent() {
      this.currentSeq = null
      clearCurrentSeq()
    },
    // 列表（按 lastAt 倒序）+ 关键字过滤
    list(keyword) {
      const sorted = [...this.patients].sort((a, b) => (b.lastAt || 0) - (a.lastAt || 0))
      return searchPatients(sorted, keyword)
    }
  }
})

export function usePatientStoreWithOut() {
  return usePatientStore(store)
}
```

- [ ] **Step 2: 追加导出**

`store/modules/index.js` 末尾追加：

```js
export * from './patient'
```

- [ ] **Step 3: 验证**

H5 控制台：`const ps = usePatientStoreWithOut(); ps.create({name:'张三',phone:'13812346543'})` → `ps.current.name === '张三'`、`ps.currentId === '#00001'`；再 `create` 一个，`ps.list('张三').length` 正确；刷新页面后 `ps.patients` 仍在（持久化）。逐条核对。

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/store/modules/patient.js 蓝牙uniapp/store/modules/index.js
git commit -m "feat(store): add patient store (list + current patient)"
```

---

### Task 6: 核心组件 CaInput / CaCard / CaEmpty

**Files:**
- Create: `蓝牙uniapp/components/base/CaInput.vue`
- Create: `蓝牙uniapp/components/base/CaCard.vue`
- Create: `蓝牙uniapp/components/base/CaEmpty.vue`

> easycom 已开启 `autoscan`，`components/` 下的组件可直接以文件名标签使用（如 `<CaInput>`）。

- [ ] **Step 1: CaInput.vue**

```vue
<template>
  <view class="ca-field">
    <view class="ca-label" v-if="label">
      {{ label }}<text v-if="required" class="ca-req"> *</text>
    </view>
    <view class="ca-input">
      <text v-if="icon" class="ca-ic">{{ icon }}</text>
      <input
        class="ca-ipt"
        :type="type"
        :password="password"
        :placeholder="placeholder"
        :value="modelValue"
        placeholder-class="ca-ph"
        @input="$emit('update:modelValue', $event.detail.value)"
      />
    </view>
  </view>
</template>

<script setup>
defineProps({
  label: String, placeholder: String, icon: String,
  modelValue: [String, Number],
  type: { type: String, default: 'text' },
  password: { type: Boolean, default: false },
  required: { type: Boolean, default: false }
})
defineEmits(['update:modelValue'])
</script>

<style lang="scss" scoped>
.ca-field { margin-bottom: 24rpx; }
.ca-label { @include ca-font; font-size: 24rpx; color: $ca-t2; font-weight: 600; margin: 0 4rpx 12rpx; }
.ca-req { color: $ca-danger; }
.ca-input {
  display: flex; align-items: center; gap: 16rpx;
  background: #fff; border: 1rpx solid $ca-border; border-radius: $ca-radius-input;
  padding: 24rpx 26rpx;
}
.ca-ic { font-size: 30rpx; }
.ca-ipt { @include ca-font; flex: 1; font-size: 28rpx; color: $ca-t1; }
.ca-ph { color: $ca-t3; }
</style>
```

- [ ] **Step 2: CaCard.vue**

```vue
<template>
  <view class="ca-card">
    <view class="ca-card-h" v-if="title">{{ title }}</view>
    <slot />
  </view>
</template>

<script setup>
defineProps({ title: String })
</script>

<style lang="scss" scoped>
.ca-card {
  background: #fff; border: 1rpx solid $ca-border; border-radius: $ca-radius-card;
  padding: 32rpx; margin-bottom: 28rpx; box-shadow: $ca-shadow-card;
}
.ca-card-h { @include ca-font; font-size: 28rpx; font-weight: 700; color: $ca-t1; margin-bottom: 20rpx; }
</style>
```

- [ ] **Step 3: CaEmpty.vue**

```vue
<template>
  <view class="ca-empty">
    <view class="ca-ei">{{ icon }}</view>
    <view class="ca-et">{{ title }}</view>
    <view class="ca-ed"><slot>{{ desc }}</slot></view>
    <view class="ca-eb" v-if="button" @tap="$emit('action')">{{ button }}</view>
  </view>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '📭' },
  title: String, desc: String, button: String
})
defineEmits(['action'])
</script>

<style lang="scss" scoped>
.ca-empty { @include ca-font; text-align: center; padding: 100rpx 48rpx; }
.ca-ei { font-size: 96rpx; opacity: .25; }
.ca-et { font-size: 32rpx; font-weight: 700; color: $ca-t1; margin-top: 28rpx; }
.ca-ed { font-size: 26rpx; color: $ca-t3; margin-top: 16rpx; line-height: 1.6; }
.ca-eb { margin-top: 40rpx; display: inline-block; background: $ca-primary; color: #fff; font-size: 28rpx; font-weight: 600; padding: 24rpx 52rpx; border-radius: 24rpx; }
</style>
```

- [ ] **Step 4: 验证**

临时在 `pages/home/home.vue` 顶部放 `<CaInput label="测试" placeholder="x" icon="🔒"/>`、`<CaEmpty title="暂无" desc="说明"/>`，H5 预览三组件渲染正常、样式符合 `components.html`。核对后移除临时代码。

- [ ] **Step 5: Commit（可选）**

```bash
git add 蓝牙uniapp/components/base/CaInput.vue 蓝牙uniapp/components/base/CaCard.vue 蓝牙uniapp/components/base/CaEmpty.vue
git commit -m "feat(ui): add CaInput/CaCard/CaEmpty base components"
```

---

### Task 7: 核心组件 CaMetric / CaStatusStrip / CaPatientBar

**Files:**
- Create: `蓝牙uniapp/components/base/CaMetric.vue`
- Create: `蓝牙uniapp/components/base/CaStatusStrip.vue`
- Create: `蓝牙uniapp/components/base/CaPatientBar.vue`

- [ ] **Step 1: CaMetric.vue（指标卡，含左/右）**

```vue
<template>
  <view class="ca-m">
    <view class="ca-mk">{{ label }}</view>
    <view class="ca-mv">{{ value }}<text class="ca-mu" v-if="unit"> {{ unit }}</text></view>
    <view class="ca-mlr" v-if="left !== undefined || right !== undefined">
      <text v-if="left !== undefined">左 <text class="b">{{ left }}</text></text>
      <text v-if="right !== undefined">右 <text class="b">{{ right }}</text></text>
    </view>
  </view>
</template>

<script setup>
defineProps({ label: String, value: [String, Number], unit: String, left: [String, Number], right: [String, Number] })
</script>

<style lang="scss" scoped>
.ca-m { @include ca-font; background: #fff; border: 1rpx solid $ca-border; border-radius: 28rpx; padding: 26rpx; }
.ca-mk { font-size: 23rpx; color: $ca-t2; }
.ca-mv { font-size: 44rpx; font-weight: 700; color: $ca-t1; margin-top: 6rpx; }
.ca-mu { font-size: 22rpx; color: $ca-t3; font-weight: 600; }
.ca-mlr { display: flex; gap: 20rpx; margin-top: 12rpx; font-size: 21rpx; color: $ca-t2; }
.ca-mlr .b { color: $ca-t1; }
</style>
```

- [ ] **Step 2: CaStatusStrip.vue（采集中状态条）**

```vue
<template>
  <view class="ca-strip">
    <view class="ca-dot" />
    <view class="ca-txt">
      <view class="ca-t1l">{{ title }}</view>
      <view class="ca-t2l">{{ sub }}</view>
    </view>
  </view>
</template>

<script setup>
defineProps({ title: String, sub: String })
</script>

<style lang="scss" scoped>
.ca-strip { @include ca-font; display: flex; align-items: center; gap: 18rpx; background: #fdf2e2; border: 1rpx solid #f3dcb4; border-radius: 24rpx; padding: 22rpx 26rpx; margin-bottom: 28rpx; }
.ca-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: $ca-warning; animation: caPulse 1.1s infinite; }
@keyframes caPulse { 50% { opacity: .25; } }
.ca-t1l { font-size: 26rpx; font-weight: 600; color: #a96a12; }
.ca-t2l { font-size: 22rpx; color: #b5853a; }
</style>
```

- [ ] **Step 3: CaPatientBar.vue（当前患者条）**

```vue
<template>
  <view class="ca-pb" @tap="onSwitch">
    <view class="ca-av">{{ avatar }}</view>
    <view class="ca-info">
      <view class="ca-nm">{{ name }}</view>
      <view class="ca-id">{{ sub }}</view>
    </view>
    <view class="ca-sw">切换 ⇄</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
const ps = usePatientStoreWithOut()
const name = computed(() => ps.current?.name || '未选择患者')
const avatar = computed(() => (ps.current?.name || '?').slice(0, 1))
const sub = computed(() => {
  const p = ps.current
  if (!p) return '点此选择患者'
  return [ps.currentId, p.gender, p.age ? p.age + '岁' : ''].filter(Boolean).join(' · ')
})
function onSwitch() {
  uni.navigateTo({ url: '/pages/patient/select' })
}
</script>

<style lang="scss" scoped>
.ca-pb { @include ca-font; display: flex; align-items: center; gap: 20rpx; background: #fff; border-bottom: 1rpx solid $ca-border; padding: 20rpx 28rpx; }
.ca-av { width: 68rpx; height: 68rpx; border-radius: 20rpx; background: $ca-primary-light; color: $ca-primary; display: flex; align-items: center; justify-content: center; font-size: 30rpx; font-weight: 700; }
.ca-info { flex: 1; }
.ca-nm { font-size: 28rpx; font-weight: 700; color: $ca-t1; }
.ca-id { font-size: 22rpx; color: $ca-t3; margin-top: 2rpx; }
.ca-sw { font-size: 24rpx; color: $ca-primary; font-weight: 600; }
</style>
```

- [ ] **Step 4: 验证**

临时挂到 home.vue 顶部核对三组件渲染与 `components.html` / `page-setup-patient.html`（患者条）一致；CaPatientBar 在已 `create` 患者时显示姓名+编号，点按跳 `patient/select`（该页 Task 10 才有，先确认跳转触发即可）。核对后移除临时代码。

- [ ] **Step 5: Commit（可选）**

```bash
git add 蓝牙uniapp/components/base/CaMetric.vue 蓝牙uniapp/components/base/CaStatusStrip.vue 蓝牙uniapp/components/base/CaPatientBar.vue
git commit -m "feat(ui): add CaMetric/CaStatusStrip/CaPatientBar components"
```

---

## Phase 1 — 入口与就诊流程

### Task 8: 路由表 + 启动网关

**Files:**
- Modify: `蓝牙uniapp/pages.json`
- Modify: `蓝牙uniapp/App.vue`

- [ ] **Step 1: 在 pages.json 的 `pages` 数组追加新页面**

在 `pages` 数组中**追加**以下四项（保持 `pages/home/home` 仍为第 0 项 / 默认页）：

```json
{ "path": "pages/setup/enable",  "style": { "navigationStyle": "custom" } },
{ "path": "pages/setup/unlock",  "style": { "navigationStyle": "custom" } },
{ "path": "pages/patient/select","style": { "navigationBarTitleText": "选择患者" } },
{ "path": "pages/patient/new",   "style": { "navigationBarTitleText": "新建患者" } }
```

> 暂不删除 `pages/login/login`、`pages/register/register`（Task 14 统一清理），避免中途引用报错。

- [ ] **Step 2: App.vue onLaunch 写启动网关**

把 `蓝牙uniapp/App.vue` 的 `<script>` 改为：

```js
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()
    blueToothStore.initBle()

    const op = useOperatorStoreWithOut()
    const ps = usePatientStoreWithOut()

    // 网关：未启用 → 启用页；已启用未解锁 → 解锁页；已解锁未选患者 → 选患者；否则进首页
    if (!op.isEnabled) {
      uni.reLaunch({ url: '/pages/setup/enable' })
    } else if (!op.unlocked) {
      uni.reLaunch({ url: '/pages/setup/unlock' })
    } else if (!ps.current) {
      uni.reLaunch({ url: '/pages/patient/select' })
    }
    // 已启用+已解锁+有当前患者：留在默认首页
  },
  onShow() {}, onHide() {}
}
```

> 用 `reLaunch` 清栈，避免回退到网关后面的页。首页是 tabBar 页，从 `patient/select` 选完患者后用 `uni.switchTab` 进首页（见 Task 10）。

- [ ] **Step 3: 验证（验收清单）**

清掉本地存储（H5：Application→Clear storage，或调用 `uni.clearStorageSync()`）后重启预览：
1. 首次启动落到 **启用页**。
2. （启用页做完后回归再测）已启用未解锁 → **解锁页**。
3. 已解锁未选患者 → **选患者页**。
4. 选了患者再启动 → **首页**。
（本任务先验证 1 能跳转；2-4 待对应页完成后回归。）

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/pages.json 蓝牙uniapp/App.vue
git commit -m "feat(routing): add setup/patient routes and launch gate"
```

---

### Task 9: 首次启用页 + 解锁页

**Files:**
- Create: `蓝牙uniapp/pages/setup/enable.vue`
- Create: `蓝牙uniapp/pages/setup/unlock.vue`

视觉对照 `page-setup-patient.html` 屏 1、屏 2。

- [ ] **Step 1: enable.vue**

```vue
<template>
  <view class="page">
    <view class="hero">
      <view class="logo">🦶</view>
      <view class="h1">步态采集系统</view>
      <view class="h2">首次启用 · 请填写本机操作信息</view>
    </view>
    <CaInput label="医院" icon="🏥" placeholder="如：市第一人民医院" v-model="f.hospital" />
    <CaInput label="科室" icon="🩺" placeholder="如：康复科" v-model="f.dept" />
    <CaInput label="医生姓名" icon="👤" placeholder="请输入您的姓名" v-model="f.name" />
    <CaInput label="联系方式" icon="📞" type="number" placeholder="手机号" v-model="f.phone" />
    <CaInput label="设置口令" icon="🔒" :password="true" placeholder="自设一个本机口令" v-model="f.passcode" />
    <view class="btn" @tap="onEnable">启用本机</view>
    <view class="hint">仅本机填写一次，之后无需重复登录。\n口令用于打开 App，丢失设备可防数据泄露。</view>
  </view>
</template>

<script setup>
import { reactive } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { isValidPhone } from '@/utils/patient'
const op = useOperatorStoreWithOut()
const f = reactive({ hospital: '', dept: '', name: '', phone: '', passcode: '' })
function onEnable() {
  if (!f.hospital || !f.dept || !f.name) return uni.showToast({ title: '请填写医院/科室/姓名', icon: 'none' })
  if (!isValidPhone(f.phone)) return uni.showToast({ title: '请输入正确手机号', icon: 'none' })
  if (!f.passcode || f.passcode.length < 4) return uni.showToast({ title: '口令至少 4 位', icon: 'none' })
  op.enable({ ...f })
  uni.reLaunch({ url: '/pages/patient/select' })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.hero { text-align: center; padding: 52rpx 0 36rpx; }
.logo { width: 116rpx; height: 116rpx; border-radius: 36rpx; background: $ca-primary-light; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto; }
.h1 { font-size: 38rpx; font-weight: 800; color: $ca-t1; margin-top: 24rpx; }
.h2 { font-size: 25rpx; color: $ca-t2; margin-top: 10rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; white-space: pre-line; }
</style>
```

- [ ] **Step 2: unlock.vue**

```vue
<template>
  <view class="page">
    <view class="hero">
      <view class="logo">🦶</view>
      <view class="h1">步态采集系统</view>
      <view class="h2">{{ subtitle }}</view>
    </view>
    <CaInput label="口令" icon="🔒" :password="true" placeholder="输入口令解锁" v-model="passcode" />
    <view class="btn" @tap="onUnlock">解锁</view>
    <view class="hint">日常打开只需输一次口令。\n非本人？<text class="link" @tap="onReset">重新启用本机</text></view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'
const op = useOperatorStoreWithOut()
const ps = usePatientStoreWithOut()
const passcode = ref('')
const subtitle = computed(() => {
  const o = op.operator || {}
  return [o.hospital, o.dept, o.name].filter(Boolean).join(' · ')
})
function onUnlock() {
  if (!op.unlock(passcode.value)) return uni.showToast({ title: '口令错误', icon: 'none' })
  if (ps.current) uni.switchTab({ url: '/pages/home/home' })
  else uni.reLaunch({ url: '/pages/patient/select' })
}
function onReset() {
  uni.showModal({
    title: '重新启用本机', content: '将清除本机操作员信息，确定？',
    success: (r) => { if (r.confirm) { op.reset(); uni.reLaunch({ url: '/pages/setup/enable' }) } }
  })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.hero { text-align: center; padding: 120rpx 0 36rpx; }
.logo { width: 116rpx; height: 116rpx; border-radius: 36rpx; background: $ca-primary-light; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto; }
.h1 { font-size: 38rpx; font-weight: 800; color: $ca-t1; margin-top: 24rpx; }
.h2 { font-size: 25rpx; color: $ca-t2; margin-top: 10rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; white-space: pre-line; }
.link { color: $ca-primary; }
</style>
```

- [ ] **Step 3: 验证（验收清单）**

1. 清存储→启动→启用页：必填校验生效；填合法值点「启用本机」→ 跳选患者页；重启 App 不再回启用页（已持久化）。
2. 已启用→手动 `op.unlocked=false` 后重启→解锁页：错口令 toast「口令错误」；对口令→有当前患者进首页 / 无则进选患者页。
3. 解锁页「重新启用本机」→ 确认后回启用页且档案被清。

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/pages/setup/enable.vue 蓝牙uniapp/pages/setup/unlock.vue
git commit -m "feat(setup): add device enable + unlock pages"
```

---

### Task 10: 患者选择页 + 新建患者页

**Files:**
- Create: `蓝牙uniapp/pages/patient/select.vue`
- Create: `蓝牙uniapp/pages/patient/new.vue`

视觉对照 `page-setup-patient.html` 屏 3、屏 4。

- [ ] **Step 1: select.vue**

```vue
<template>
  <view class="page">
    <view class="srch">
      <text>🔍</text>
      <input class="srch-ipt" placeholder="搜索姓名 / 手机号 / 编号" placeholder-class="srch-ph"
        :value="kw" @input="kw = $event.detail.value" />
    </view>
    <view class="newbtn" @tap="goNew"><text class="plus">＋</text>新建患者</view>

    <view class="pl-h">
      <text class="t">最近采集</text>
      <text class="t muted">共 {{ all.length }} 人</text>
    </view>

    <CaEmpty v-if="list.length === 0" icon="🧑‍⚕️" title="还没有患者"
      desc="点上方「新建患者」录入第一位患者" />

    <view v-for="p in list" :key="p.seq" class="pcell" @tap="onPick(p.seq)">
      <view class="av">{{ p.name.slice(0,1) }}</view>
      <view class="info">
        <view class="nm">{{ p.name }} <text class="ph">{{ mask(p.phone) }}</text></view>
        <view class="meta">{{ id(p.seq) }} · 最近 {{ fmtDate(p.lastAt) }} · {{ p.count || 0 }} 次采集</view>
      </view>
      <text class="arr">›</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { maskPhone, formatSubjectId } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const kw = ref('')
const all = computed(() => ps.patients)
const list = computed(() => ps.list(kw.value))
const mask = maskPhone
const id = formatSubjectId
function fmtDate(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function goNew() { uni.navigateTo({ url: '/pages/patient/new' }) }
function onPick(seq) {
  ps.select(seq)
  uni.switchTab({ url: '/pages/home/home' })
}
onShow(() => { /* 从新建页返回时列表自动随 store 更新 */ })
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 28rpx 32rpx; }
.srch { display: flex; align-items: center; gap: 16rpx; background: #eef1f5; border-radius: 22rpx; padding: 20rpx 24rpx; margin-bottom: 24rpx; }
.srch-ipt { flex: 1; font-size: 26rpx; color: $ca-t1; }
.srch-ph { color: $ca-t3; }
.newbtn { display: flex; align-items: center; justify-content: center; gap: 14rpx; border: 3rpx dashed #c7d2e3; color: $ca-primary; font-size: 28rpx; font-weight: 700; border-radius: 26rpx; padding: 26rpx; margin-bottom: 24rpx; background: #fbfcfe; }
.plus { font-size: 34rpx; }
.pl-h { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18rpx; }
.pl-h .t { font-size: 24rpx; color: $ca-t2; font-weight: 600; }
.pl-h .muted { color: $ca-t3; }
.pcell { display: flex; align-items: center; gap: 22rpx; background: #fff; border: 1rpx solid $ca-border; border-radius: 26rpx; padding: 24rpx 26rpx; margin-bottom: 18rpx; }
.pcell .av { width: 76rpx; height: 76rpx; border-radius: 22rpx; background: $ca-primary-light; color: $ca-primary; display: flex; align-items: center; justify-content: center; font-size: 30rpx; font-weight: 700; }
.pcell .info { flex: 1; }
.pcell .nm { font-size: 29rpx; font-weight: 700; color: $ca-t1; }
.pcell .ph { font-size: 22rpx; color: $ca-t3; font-weight: 500; }
.pcell .meta { font-size: 22rpx; color: $ca-t3; margin-top: 4rpx; }
.pcell .arr { color: $ca-t3; font-size: 32rpx; }
</style>
```

- [ ] **Step 2: new.vue**

```vue
<template>
  <view class="page">
    <CaInput label="姓名" icon="👤" required placeholder="患者姓名" v-model="f.name" />
    <CaInput label="手机号" icon="📞" required type="number" placeholder="必填 · 同名患者靠它区分" v-model="f.phone" />
    <view class="row2">
      <view class="col">
        <view class="lab">性别</view>
        <view class="seg">
          <view :class="['seg-i', f.gender==='男'&&'on']" @tap="f.gender='男'">男</view>
          <view :class="['seg-i', f.gender==='女'&&'on']" @tap="f.gender='女'">女</view>
        </view>
      </view>
      <view class="col">
        <CaInput label="年龄" type="number" placeholder="岁" v-model="f.age" />
      </view>
    </view>
    <view class="lab">患者编号</view>
    <view class="idrow"><text class="idtag">{{ nextId }} 自动生成</text><text class="idnote">导出科研只用此编号</text></view>
    <view class="btn" @tap="onCreate">创建并设为当前患者</view>
    <view class="hint">姓名仅本机供医护辨认；对外导出默认去标识化，只带编号。</view>
  </view>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { validatePatient, formatSubjectId, nextSeq } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const f = reactive({ name: '', phone: '', gender: '', age: '' })
const nextId = computed(() => formatSubjectId(nextSeq(ps.patients)))
function onCreate() {
  const v = validatePatient(f)
  if (!v.ok) return uni.showToast({ title: v.msg, icon: 'none' })
  ps.create({ ...f })
  uni.switchTab({ url: '/pages/home/home' })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.row2 { display: flex; gap: 20rpx; }
.col { flex: 1; }
.lab { font-size: 24rpx; color: $ca-t2; font-weight: 600; margin: 0 4rpx 12rpx; }
.seg { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.seg-i { flex: 1; text-align: center; padding: 22rpx; border-radius: 20rpx; border: 1rpx solid $ca-border; background: #fff; font-size: 26rpx; color: $ca-t2; }
.seg-i.on { border-color: $ca-primary; color: $ca-primary; background: $ca-primary-light; font-weight: 700; }
.idrow { display: flex; align-items: center; gap: 18rpx; }
.idtag { background: #eaf7f0; color: $ca-success; font-size: 22rpx; font-weight: 700; padding: 14rpx 24rpx; border-radius: 18rpx; }
.idnote { font-size: 22rpx; color: $ca-t3; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; }
</style>
```

- [ ] **Step 3: 验证（验收清单）**

1. 选患者页：搜索框输姓名/手机号/编号能过滤；无患者时显示空态。
2. 「新建患者」→ 姓名空 / 手机号非法各自 toast；编号显示「#0000X 自动生成」随列表递增。
3. 创建后回到首页（tabBar），首页顶部患者条显示新患者姓名+编号（依赖 Task 12）。
4. 列表项展示脱敏手机号；造两个同名患者用手机号能搜出区分。

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/pages/patient/select.vue 蓝牙uniapp/pages/patient/new.vue
git commit -m "feat(patient): add patient select + new pages"
```

---

## Phase 2 — 功能页重做

### Task 11: 设备连接 & 采集（mine.vue 设备区）

> `pages/mine/mine.vue` 现含设备管理（连接/断开/加设备 QR/删除）。本任务：套用新视觉、复用 `blueToothStore` 现有 action、移除**采样频率/单独开关**控制、删除设备名「(一双)」与「正在采集（左+右）」文案、采集中用 `CaStatusStrip`。视觉对照 `page-device-v4.html`。

**Files:**
- Modify: `蓝牙uniapp/pages/mine/mine.vue`

- [ ] **Step 1: 定位并移除不可控控件**

在 `mine.vue` 搜索并删除：采样频率相关（`showHzActionSheet` / `1HZ/5HZ/10HZ` 选项及其入口）、单独开关相关（`showSwitchActionSheet` 入口）、设备名里的 `(一双)` 文案、采集中「正在采集（左+右）」文案。保留 `connectDevice`/`disconnectDevice`/`addDevice`/`deleteDevice` 调用。

- [ ] **Step 2: 顶部加当前患者条 + 采集归属**

在 `mine.vue` 模板设备区上方加：

```vue
<CaPatientBar />
<view class="attr">本次采集归属：{{ attrText }}</view>
```

script 内：

```js
import { computed } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
const op = useOperatorStoreWithOut()
const attrText = computed(() => {
  const a = op.attribution()
  return [a.hospital, a.dept, a.doctor].filter(Boolean).join(' · ') || '未设置'
})
```

样式：

```scss
.attr { @include ca-font; font-size: 22rpx; color: $ca-t2; background: #eaf7f0; border-radius: 18rpx; padding: 16rpx 22rpx; margin: 20rpx 0; }
```

- [ ] **Step 3: 采集中状态用 CaStatusStrip**

设备处于采集状态时，用：

```vue
<CaStatusStrip v-if="isCollecting" title="鞋垫 A 采集中" :sub="collectSub" />
```

`isCollecting` / `collectSub`（计时 + 已上传条数）按 `blueToothStore` 现有连接/数据状态推导；若现状无「采集中」标志位，用「已连接 + 正在收 notify 数据」近似（与现有逻辑一致，不新增协议）。停止按钮调用现有 `disconnectDevice(id)` 或现有停止逻辑。

- [ ] **Step 4: 套用新卡片视觉**

设备卡片改用 `CaCard` 容器与 tokens 配色，字体走 `@include ca-font`（非等宽/非 Segoe UI），按钮主色 `$ca-primary`、停止用 `$ca-danger`。布局对照 `page-device-v4.html`。

- [ ] **Step 5: 验证（验收清单）**

真机（蓝牙）/H5（视觉）：
1. 无采样频率、无单独开关入口；无「(一双)」「正在采集（左+右）」文案。
2. 顶部患者条 + 采集归属正确显示。
3. 连接/断开/加设备（扫码）/删除 仍可用（真机核对）。
4. 采集态显示橙色状态条（计时/条数）。
5. 视觉与 `page-device-v4.html` 一致。

- [ ] **Step 6: Commit（可选）**

```bash
git add 蓝牙uniapp/pages/mine/mine.vue
git commit -m "feat(device): restyle device/collect, drop uncontrollable controls"
```

---

### Task 12: 首页实时（足底图保持原样）

> **足底压力区（`.foot-card` + `.foot-bg` + `.dot` + ripple 动画 + `pointsPercent`/`rightPoints`）整段保持不变**。只重做顶部患者条、实时参数区（改 `CaMetric` 卡）、空态。视觉对照 `page-home-v3.html`。

**Files:**
- Modify: `蓝牙uniapp/pages/home/home.vue`

- [ ] **Step 1: 顶部加患者条**

模板最外层 `.container` 内最前面加 `<CaPatientBar />`。

- [ ] **Step 2: 参数区改为 CaMetric 网格**

把现有「左右脚实时参数」`.section`（行 13-39）替换为：

```vue
<view class="mh">实时参数</view>
<view class="mgrid" v-if="hasData">
  <CaMetric label="步速" :value="rt.avg.speed" unit="m/s" :left="rt.left.speed" :right="rt.right.speed" />
  <CaMetric label="步长" :value="rt.avg.length" unit="cm" :left="rt.left.length" :right="rt.right.length" />
  <CaMetric label="单支撑时间" :value="rt.avg.leftSingle" unit="s" :left="rt.left.single" :right="rt.right.single" />
  <CaMetric label="双支撑时间" :value="rt.avg.double" unit="s" :left="rt.left.double" :right="rt.right.double" />
</view>
<CaEmpty v-else icon="👣" title="还没有开始采集" desc="连接鞋垫并开始采集后，这里会实时显示步态参数" />
```

script 增加：

```js
import { computed } from 'vue'
// 真实数据接入前：无数据 → 走空态（不再显示一排 '-'）
const hasData = computed(() => rt.left.speed !== '-' )
```

样式：

```scss
.mh { @include ca-font; font-size: 30rpx; font-weight: 700; color: $ca-t1; margin: 24rpx 4rpx 20rpx; }
.mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; }
```

- [ ] **Step 3: 验证（验收清单）**

1. 足底图与改前**完全一致**（原 foot.png + 蓝点 + ripple）。
2. 顶部患者条显示当前患者。
3. 无数据时显示空态，**不再出现一排 `-`**。
4. （临时把 `rt.left.speed` 改成数值可看到参数卡渲染，核对后改回 `-`。）
5. 视觉与 `page-home-v3.html` 一致。

- [ ] **Step 4: Commit（可选）**

```bash
git add 蓝牙uniapp/pages/home/home.vue
git commit -m "feat(home): restyle realtime params, keep foot pressure as-is"
```

---

### Task 13: 数据分析页重做

> 干掉 6 个 `0.000000` arcbar 三连，改为：顶部时间分段 + 2×2 KPI 概览 + 折线（步速趋势）+ 分组柱（左右脚压力 / 单支撑）；无数据空态。沿用 `qiun-data-charts` + `getRingOpts/getBarOpts`（折线可用 `type="line"`）。视觉对照 `page-data.html`。

**Files:**
- Modify: `蓝牙uniapp/pages/data/data.vue`

- [ ] **Step 1: 重写 template**

```vue
<template>
  <view class="container">
    <CaPatientBar />
    <view class="body">
      <!-- 时间分段 -->
      <view class="seg">
        <view v-for="(t,i) in ranges" :key="i" :class="['seg-i', range===i&&'on']" @tap="range=i">{{ t }}</view>
      </view>

      <block v-if="hasData">
        <!-- KPI 概览 -->
        <view class="kpi">
          <view class="k" v-for="(k,i) in kpis" :key="i">
            <view class="kk">{{ k.label }}</view>
            <view class="kv">{{ k.value }}<text class="ks"> {{ k.unit }}</text></view>
            <view :class="['kd', k.up ? 'up':'down']">{{ k.up ? '▲':'▼' }} {{ k.delta }}</view>
          </view>
        </view>

        <CaCard title="步速趋势">
          <qiun-data-charts type="line" :opts="lineOpts" :chartData="lineData" />
        </CaCard>
        <CaCard title="左右脚压力对比">
          <qiun-data-charts type="column" :opts="barOpts" :chartData="pressureData" />
        </CaCard>
        <CaCard title="单支撑时间（左/右）">
          <qiun-data-charts type="column" :opts="barOpts" :chartData="singleData" />
        </CaCard>
      </block>

      <CaEmpty v-else icon="📊" title="暂无数据" desc="完成一次采集后，这里会显示步态统计与趋势分析" />
    </view>
  </view>
</template>
```

- [ ] **Step 2: 重写 script（示意数据，待真实接入替换）**

```vue
<script setup>
import { ref, computed } from 'vue'
import { getBarOpts } from '@/utils/ucharts'

const ranges = ['本周', '上周', '本月', '近半年']
const range = ref(0)

// 真实数据接入前：默认有示意数据；接入后用「该时间段是否有该患者数据」驱动
const hasData = ref(true)

const kpis = computed(() => ([
  { label: '平均步数', value: '6,820', unit: '步', up: true, delta: '8% 较上周' },
  { label: '平均步速', value: '1.24', unit: 'm/s', up: true, delta: '3%' },
  { label: '平均步长', value: '66', unit: 'cm', up: false, delta: '2%' },
  { label: '双支撑时长', value: '0.19', unit: 's', up: true, delta: '1%' }
]))

const lineOpts = { color: ['#2F6DF6'], padding: [10, 10, 0, 10], legend: { show: false },
  xAxis: { disableGrid: true }, yAxis: { gridType: 'dash' },
  extra: { line: { type: 'curve', width: 2 } } }
const lineData = ref({
  categories: ['一', '二', '三', '四', '五', '六', '日'],
  series: [{ name: '步速', data: [1.1, 1.18, 1.15, 1.27, 1.22, 1.33, 1.3] }]
})

const barOpts = getBarOpts({ legend: { show: true } })
const pressureData = ref({
  categories: ['本周', '上周', '本月', '半年'],
  series: [
    { name: '左', data: [70, 58, 50, 80], color: '#2F6DF6' },
    { name: '右', data: [64, 62, 46, 74], color: '#15A05A' }
  ]
})
const singleData = ref({
  categories: ['本周', '上周', '本月'],
  series: [
    { name: '左', data: [0.6, 0.52, 0.44], color: '#2F6DF6' },
    { name: '右', data: [0.55, 0.5, 0.48], color: '#15A05A' }
  ]
})
</script>
```

- [ ] **Step 3: 写 style**

```vue
<style lang="scss" scoped>
.container { @include ca-font; }
.body { padding: 28rpx 32rpx; }
.seg { display: flex; background: #eef1f5; border-radius: 22rpx; padding: 6rpx; margin-bottom: 28rpx; }
.seg-i { flex: 1; text-align: center; font-size: 25rpx; font-weight: 600; color: $ca-t2; padding: 16rpx; border-radius: 16rpx; }
.seg-i.on { background: #fff; color: $ca-primary; box-shadow: 0 1rpx 3rpx rgba(0,0,0,.08); }
.kpi { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 28rpx; }
.k { background: #fff; border: 1rpx solid $ca-border; border-radius: 28rpx; padding: 26rpx; }
.kk { font-size: 23rpx; color: $ca-t2; }
.kv { font-size: 42rpx; font-weight: 700; color: $ca-t1; margin-top: 6rpx; }
.ks { font-size: 22rpx; color: $ca-t3; }
.kd { font-size: 22rpx; margin-top: 8rpx; font-weight: 600; }
.kd.up { color: $ca-success; }
.kd.down { color: $ca-danger; }
</style>
```

- [ ] **Step 4: 验证（验收清单）**

1. **页面再无 `0.000000`**。
2. 顶部时间分段可切换高亮。
3. KPI 2×2 显示 + 环比上升绿/下降红。
4. 折线 + 两个分组柱正常渲染（H5）。
5. 把 `hasData` 临时设 `false` → 显示空态。
6. 视觉与 `page-data.html` 一致。

> 真实数据接入计划落地时：用 patientStore.current + range 调后端按患者聚合接口替换示意数据，并用接口返回是否为空驱动 `hasData`。

- [ ] **Step 5: Commit（可选）**

```bash
git add 蓝牙uniapp/pages/data/data.vue
git commit -m "feat(data): rebuild analysis page (range + KPI + charts + empty)"
```

---

### Task 14: 我的页精简 + 操作员资料 + 清理死代码

**Files:**
- Modify: `蓝牙uniapp/pages/mine/mine.vue`
- Delete: `蓝牙uniapp/pages/login/login.vue`, `蓝牙uniapp/pages/register/register.vue`, `蓝牙uniapp/pages/data/data copy.vue`, `蓝牙uniapp/pages/home/home copy.vue`
- Modify: `蓝牙uniapp/pages.json`

- [ ] **Step 1: 我的页加操作员资料卡 + 重新启用入口**

在 `mine.vue` 顶部用 `CaCard` 展示操作员：医院/科室/医生/联系方式（来自 `operatorStore.operator`），底部一个「重新启用本机」按钮：

```js
function reEnable() {
  uni.showModal({ title: '重新启用本机', content: '将清除本机操作员信息并退出，确定？',
    success: (r) => { if (r.confirm) { op.reset(); uni.reLaunch({ url: '/pages/setup/enable' }) } } })
}
```

移除 `mine.vue` 里残留的「个人中心/用户头像/旧 userStore 登录」类无用块（操作员模型下不再有 App 账号概念）。

- [ ] **Step 2: 删除登录/注册/死文件**

删除 `pages/login/login.vue`、`pages/register/register.vue`、`pages/data/data copy.vue`、`pages/home/home copy.vue`。从 `pages.json` 的 `pages` 数组移除 `pages/login/login`、`pages/register/register`（及不再使用的 `pages/mine/profile` 若已无入口）。

- [ ] **Step 3: 清理引用**

全局搜索 `login`、`register`、`networkDiagnostic`、`userLoginApi`、`userStore` 的残留 import / 跳转；删除或改向新流程。确认 `utils/networkDiagnostic.js` 不再被任何页面 import（保留文件无妨，但不在 UI 暴露）。

- [ ] **Step 4: 验证（验收清单）**

1. 全量编译无「找不到页面/模块」报错。
2. 我的页显示操作员资料；「重新启用本机」可回到启用页。
3. App 内已无登录/注册/网络诊断入口。
4. tabBar 三页（首页/数据/我的）正常切换。

- [ ] **Step 5: Commit（可选）**

```bash
git add -A 蓝牙uniapp/
git commit -m "chore: simplify mine page, remove login/register and dead files"
```

---

### Task 15: 端到端回归

**Files:** 无（仅验证）

- [ ] **Step 1: 全流程验收（清空存储后）**

1. 首启 → 启用页 → 填写启用 → 选患者页。
2. 新建患者 → 自动编号 → 进首页（患者条正确）。
3. 首页：足底图原样 + 参数空态。
4. 我的页：连接设备（真机）/ 采集态状态条 / 无频率开关 / 采集归属正确。
5. 数据页：分段+KPI+图表，无 `0.000000`，空态可达。
6. 切换患者：任意页患者条「切换」→ 选患者页 → 换人 → 各页随当前患者变化。
7. 杀进程重开 → 解锁页 → 对口令 → 回到上次患者首页。
8. 我的页「重新启用本机」→ 清档案 → 启用页。

- [ ] **Step 2: 跑纯逻辑单测**

Run: `cd 蓝牙uniapp && npm test`
Expected: `patient.test.js` 全 PASS。

- [ ] **Step 3: Commit（可选）**

```bash
git commit --allow-empty -m "test: e2e regression pass for clinical redesign"
```

---

## Self-Review（作者已核对）

- **Spec 覆盖**：tokens(T1)、组件(T6/T7)、应用模型 operator+patient(T3/T4/T5)、启用&解锁(T9)、患者选择&新建(T10)、当前患者条(T7+各页)、设备&采集(T11)、首页足底保持原样(T12)、数据分析(T13)、我的精简+清理(T14) —— spec 第 2-7 节逐条有对应任务。
- **占位符扫描**：无 TBD/TODO；每个代码步骤含完整代码；「真实数据接入」明确标为后续计划并给出接入位置，非本计划占位。
- **类型/命名一致**：`operatorStore`(enable/unlock/reset/attribution/isEnabled/unlocked)、`patientStore`(create/select/list/current/currentId/clearCurrent)、`patient.js`(formatSubjectId/nextSeq/maskPhone/isValidPhone/validatePatient/searchPatients) 在定义任务与使用任务间签名一致；存储键集中在 `clinicStorage.js`。
- **已知风险/需实现者确认**：① mine.vue 采集态标志位以现有蓝牙连接/notify 状态近似（T11 Step3）——需对照现码确认；② 项目若无 npm 环境，T2 单测降级为手动核对（已在「测试方式」说明）；③ 后端表/接口未改，数据页与实时参数用示意/空态。
