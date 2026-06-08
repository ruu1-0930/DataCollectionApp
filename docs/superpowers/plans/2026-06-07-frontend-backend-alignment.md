# 前后端对齐（前端接入新临床后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把采集端 App（`蓝牙uniapp/`）从「纯本地存储」接到已就绪的临床后端（clinician/patient/device + 按患者历史只读），完成 `2026-06-07-frontend-backend-alignment.md` 全部 `[需改前端]` 项。

**Architecture:** 后端 scope A 已实现且契约一致（见 spec §11.1），本计划只动前端。分四相推进：① 纯逻辑地基（可单测）→ ② API 层 + token 接线（启用/登录/terminal_code/401 刷新）→ ③ 患者流程（后端发 id/subject_id）→ ④ 采集补 patient_id + 按患者历史 + 清理旧接口。可单测的纯函数走 TDD（vitest），uni/Pinia/蓝牙/网络接线只能真机+真后端（`http://118.31.39.47`）手动验证——与现有测试边界（`tests/patient.test.js` 仅测纯函数）一致。

**Tech Stack:** uni-app + Vue3 + Pinia + luch-request；vitest 1.6（仅纯函数）；后端 Flask（`Authorization: Bearer <token>`，响应包络 `{code,msg,data}`，`code===200` 取 `data.data`）。

---

## 文件结构（先定边界）

**新增（纯逻辑，单测覆盖）**
- `蓝牙uniapp/utils/terminal.js` — `generateTerminalCode()`（纯）+ `getTerminalCode()`（uni storage 包装）。职责：终端稳定标识。
- `蓝牙uniapp/utils/apiShape.js` — 后端↔前端形状映射纯函数：`normalizePatient` / `buildRawDataPayload` / `mapHistoryItem`。
- `蓝牙uniapp/tests/terminal.test.js`、`蓝牙uniapp/tests/apiShape.test.js`

**新增（API 层）**
- `蓝牙uniapp/api/clinician.js`、`api/patient.js`、`api/device.js`

**修改**
- `蓝牙uniapp/api/index.js`（导出新模块）、`api/user.js`（删旧接口，§8）
- `蓝牙uniapp/utils/request.js`（鉴权白名单 + token 源 + 401 静默刷新）
- `蓝牙uniapp/utils/patient.js`（`searchPatients` 支持 `subjectId`）
- `蓝牙uniapp/store/modules/operator.js`（async 启用/登录 + terminal_code）
- `蓝牙uniapp/store/modules/patient.js`（后端驱动 create/list/current/currentId）
- `蓝牙uniapp/store/modules/blueTooth.js`（上传补 patient_id + 无患者禁采 + 设备 API 换模块）
- 页面：`pages/setup/enable.vue`、`pages/patient/new.vue`、`pages/patient/select.vue`、`pages/data/data.vue`

**规约（贯穿全程）**
- token 整串存为 `"Bearer <jwt>"`（后端按空格切分取第 2 段，见 `back/utils.py:26`）。
- 新患者前端形状：`{ id, subjectId, name, phone, gender, age, lastAt, existed }`（`id`=后端主键，`subjectId`=后端假名如 `#00427`）。
- 不重做 §6 为「连接时注册」：沿用现有扫码加设备（spec §11.3）。

---

## Phase 0 — 纯逻辑地基（TDD）

### Task 1: 终端标识 terminal_code（§1）

**Files:**
- Create: `蓝牙uniapp/utils/terminal.js`
- Test: `蓝牙uniapp/tests/terminal.test.js`

- [ ] **Step 1: 写失败测试**

```js
// 蓝牙uniapp/tests/terminal.test.js
import { describe, it, expect } from 'vitest'
import { generateTerminalCode } from '../utils/terminal.js'

describe('generateTerminalCode', () => {
  it('生成 RFC4122 v4 形状字符串', () => {
    const code = generateTerminalCode(() => 0.5)
    expect(code).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
  it('第 3 段首位恒为版本号 4', () => {
    expect(generateTerminalCode(() => 0)[14]).toBe('4')
  })
  it('两次调用注入不同随机源得到不同值', () => {
    let i = 0
    const seq = () => [0.1, 0.9, 0.3, 0.7][(i++) % 4]
    expect(generateTerminalCode(seq)).not.toBe(generateTerminalCode(() => 0.5))
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd 蓝牙uniapp && npx vitest run tests/terminal.test.js`
Expected: FAIL（`Cannot find module '../utils/terminal.js'`）

- [ ] **Step 3: 写最小实现**

```js
// 蓝牙uniapp/utils/terminal.js —— 终端稳定标识（换机/重装视为新终端，可接受）
const TERMINAL_KEY = '__terminal_code__'

// 纯函数：用注入的 rng 生成 v4 形状字符串，便于单测
export function generateTerminalCode(rng = Math.random) {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (rng() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

// uni 包装：首次读不到则生成并持久化
export function getTerminalCode() {
  let code = ''
  try { code = uni.getStorageSync(TERMINAL_KEY) || '' } catch (e) {}
  if (!code) {
    code = generateTerminalCode()
    try { uni.setStorageSync(TERMINAL_KEY, code) } catch (e) {}
  }
  return code
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd 蓝牙uniapp && npx vitest run tests/terminal.test.js`
Expected: PASS（3 通过）

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/utils/terminal.js 蓝牙uniapp/tests/terminal.test.js
git commit -m "feat(app): 新增 terminal_code 生成与持久化（对齐 §1）"
```

---

### Task 2: 后端↔前端形状映射（§4/§5/§7）

**Files:**
- Create: `蓝牙uniapp/utils/apiShape.js`
- Test: `蓝牙uniapp/tests/apiShape.test.js`

- [ ] **Step 1: 写失败测试**

```js
// 蓝牙uniapp/tests/apiShape.test.js
import { describe, it, expect } from 'vitest'
import { normalizePatient, buildRawDataPayload, mapHistoryItem } from '../utils/apiShape.js'

describe('normalizePatient', () => {
  it('后端患者对象映射为前端形状', () => {
    const p = normalizePatient({
      id: 7, subject_id: '#00007', name: '张三', phone: '13812346543',
      gender: '男', age: 60, last_collected_at: '2026-06-07T03:00:00', existed: true
    })
    expect(p).toEqual({
      id: 7, subjectId: '#00007', name: '张三', phone: '13812346543',
      gender: '男', age: 60, lastAt: Date.parse('2026-06-07T03:00:00'), existed: true
    })
  })
  it('缺省字段安全降级', () => {
    const p = normalizePatient({ id: 1, subject_id: '#00001' })
    expect(p.gender).toBe('')
    expect(p.age).toBe('')
    expect(p.lastAt).toBe(null)
    expect(p.existed).toBe(false)
  })
})

describe('buildRawDataPayload', () => {
  it('把 patient_id 并入 38 维 apiData', () => {
    const payload = buildRawDataPayload(7, { ax: 1, ay: 2, lp1: 9 })
    expect(payload).toEqual({ patient_id: 7, ax: 1, ay: 2, lp1: 9 })
  })
})

describe('mapHistoryItem', () => {
  it('映射历史记录与 transformed', () => {
    const it = mapHistoryItem({
      id: 11, collected_at: '2026-06-07T03:00:00',
      ax: 1, ay: 2, az: 3, gx: 4, gy: 5, gz: 6, transformed: { T1: 1, T2: 2, T3: 3, T4: 4, T5: 5 }
    })
    expect(it.id).toBe(11)
    expect(it.collectedAt).toBe(Date.parse('2026-06-07T03:00:00'))
    expect(it.t).toEqual({ T1: 1, T2: 2, T3: 3, T4: 4, T5: 5 })
  })
  it('transformed 缺省为 null', () => {
    expect(mapHistoryItem({ id: 1, transformed: null }).t).toBe(null)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd 蓝牙uniapp && npx vitest run tests/apiShape.test.js`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写最小实现**

```js
// 蓝牙uniapp/utils/apiShape.js —— 后端对象 <-> 前端形状 的纯映射
export function normalizePatient(b = {}) {
  return {
    id: b.id,
    subjectId: b.subject_id,
    name: b.name,
    phone: b.phone,
    gender: b.gender || '',
    age: b.age == null ? '' : b.age,
    lastAt: b.last_collected_at ? Date.parse(b.last_collected_at) : null,
    existed: !!b.existed
  }
}

export function buildRawDataPayload(patientId, apiData) {
  return { patient_id: patientId, ...apiData }
}

export function mapHistoryItem(it = {}) {
  return {
    id: it.id,
    collectedAt: it.collected_at ? Date.parse(it.collected_at) : null,
    ax: it.ax, ay: it.ay, az: it.az, gx: it.gx, gy: it.gy, gz: it.gz,
    t: it.transformed ? { ...it.transformed } : null
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd 蓝牙uniapp && npx vitest run tests/apiShape.test.js`
Expected: PASS（5 通过）

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/utils/apiShape.js 蓝牙uniapp/tests/apiShape.test.js
git commit -m "feat(app): 新增后端↔前端形状映射纯函数（对齐 §4/§5/§7）"
```

---

### Task 3: searchPatients 支持 subjectId（§4 连带）

**Files:**
- Modify: `蓝牙uniapp/utils/patient.js:34-48`
- Test: `蓝牙uniapp/tests/patient.test.js`（追加用例）

- [ ] **Step 1: 追加失败测试**

在 `tests/patient.test.js` 末尾追加：

```js
describe('searchPatients 支持后端 subjectId', () => {
  const list = [
    { id: 7, subjectId: '#00007', name: '李雷', phone: '13812346543' },
    { id: 8, subjectId: '#00008', name: '韩梅', phone: '15912342071' }
  ]
  it('按 subjectId 字符串命中', () => {
    expect(searchPatients(list, '#00008')[0].name).toBe('韩梅')
  })
  it('按编号数字命中', () => {
    expect(searchPatients(list, '7')[0].name).toBe('李雷')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd 蓝牙uniapp && npx vitest run tests/patient.test.js`
Expected: FAIL（新用例红：当前用 `p.seq` 取编号，新对象无 `seq`）

- [ ] **Step 3: 改实现（优先用 subjectId，回退 seq，保旧测试绿）**

把 `蓝牙uniapp/utils/patient.js` 的 `searchPatients` 替换为：

```js
// 搜索：按 姓名 / 手机号 / 编号(数字或#) 匹配，返回过滤后的列表
export function searchPatients(patients, keyword) {
  const k = String(keyword || '').trim().toLowerCase()
  if (!k) return patients || []
  const kDigits = k.replace(/[^0-9]/g, '')
  return (patients || []).filter((p) => {
    const name = String(p.name || '').toLowerCase()
    const phone = String(p.phone || '')
    // 后端患者带 subjectId（#00007）；旧本地对象回退用 seq 计算
    const id = String(p.subjectId || formatSubjectId(p.seq)).toLowerCase()
    const idDigits = id.replace(/[^0-9]/g, '')
    if (name.includes(k)) return true
    if (kDigits && phone.includes(kDigits)) return true
    if (id.includes(k)) return true
    if (kDigits && idDigits.includes(kDigits)) return true
    return false
  })
}
```

- [ ] **Step 4: 运行全部纯函数测试确认通过**

Run: `cd 蓝牙uniapp && npx vitest run`
Expected: PASS（patient/terminal/apiShape 全绿）

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/utils/patient.js 蓝牙uniapp/tests/patient.test.js
git commit -m "feat(app): searchPatients 支持后端 subjectId（对齐 §4）"
```

---

## Phase 1 — API 层 + token 接线

### Task 4: 新增 clinician/patient/device API 模块（§2/§3/§4/§5/§6/§7/§8）

**Files:**
- Create: `蓝牙uniapp/api/clinician.js`、`api/patient.js`、`api/device.js`
- Modify: `蓝牙uniapp/api/index.js`

> 接线类任务无 uni mock，**验证靠 Task 12 真机回归**；本任务先把接口函数建好供后续 store 调用。

- [ ] **Step 1: 写 `api/clinician.js`**

```js
// 蓝牙uniapp/api/clinician.js
import { instance } from '@/utils'

export async function clinicianEnableApi(data) {
  // data: { hospital, dept, name, phone, terminal_code, passcode }
  return instance.request({ url: '/clinician/enable', method: 'post', data })
}
export async function clinicianLoginApi(data) {
  // data: { phone, terminal_code, passcode }
  return instance.request({ url: '/clinician/login', method: 'post', data })
}
export async function clinicianMeApi() {
  return instance.request({ url: '/clinician/me', method: 'get' })
}
export async function clinicianUpdateMeApi(data) {
  return instance.request({ url: '/clinician/me', method: 'put', data })
}
```

- [ ] **Step 2: 写 `api/patient.js`**

```js
// 蓝牙uniapp/api/patient.js
import { instance } from '@/utils'

export async function createPatientApi(data) {
  // data: { name, phone, gender, age }
  return instance.request({ url: '/patients', method: 'post', data })
}
export async function listPatientsApi() {
  return instance.request({ url: '/patients', method: 'get' })
}
export async function getPatientApi(id) {
  return instance.request({ url: `/patients/${id}`, method: 'get' })
}
export async function getPatientHistoryApi(id, params = {}) {
  // params: { start, end, page, page_size }
  return instance.request({ url: `/patients/${id}/data`, method: 'get', params })
}
```

- [ ] **Step 3: 写 `api/device.js`**

```js
// 蓝牙uniapp/api/device.js
import { instance } from '@/utils'

export async function registerDeviceApi(data) {
  // data: { device_code, device_name? }
  return instance.request({ url: '/devices', method: 'post', data })
}
export async function listDevicesApi() {
  return instance.request({ url: '/devices', method: 'get' })
}
export async function deleteDeviceApi(id) {
  return instance.request({ url: `/devices/${id}`, method: 'delete' })
}
export async function uploadRawDataApi(deviceCode, data) {
  // data: { patient_id, ...apiData(38 维) }
  return instance.request({ url: `/devices/${deviceCode}/raw_data`, method: 'post', data })
}
```

- [ ] **Step 4: 更新 `api/index.js`**

```js
// 蓝牙uniapp/api/index.js
export * from './clinician'
export * from './patient'
export * from './device'
```

> 注意：原 `export * from './user'` 在 Task 11 删除旧接口后移除；本步先并存避免引用断裂——改为：

```js
export * from './clinician'
export * from './patient'
export * from './device'
export * from './user'
```

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/api/clinician.js 蓝牙uniapp/api/patient.js 蓝牙uniapp/api/device.js 蓝牙uniapp/api/index.js
git commit -m "feat(app): 新增 clinician/patient/device API 模块（对齐 §2-§8）"
```

---

### Task 5: request.js 鉴权白名单 + token 源单一化（§10 / spec §11.3-1,2）

**Files:**
- Modify: `蓝牙uniapp/utils/request.js:96-104`

- [ ] **Step 1: 改 token 源与白名单**

把 `utils/request.js` 顶部 import：

```js
import { useUserStoreWithOut } from '@/store'
```

替换为：

```js
import { getToken } from '@/utils/auth'
```

把请求拦截器内（现 `utils/request.js:96-104`）：

```js
    const userStore = useUserStoreWithOut()
    const token = userStore.token
    if (token) {
      config.header['Authorization'] = token
    } else if (!config.url.includes('/login') && !config.url.includes('/register')) {
      return Promise.reject(config)
    }
```

替换为：

```js
    // token 由操作员启用/登录产生，存为 "Bearer xxx" 整串（auth.getToken）
    const token = getToken()
    // 无 token 仅放行启用/登录；其余无 token 请求静默取消（不强制登出，沿用旧策略）
    const noAuthPaths = ['/clinician/enable', '/clinician/login']
    if (token) {
      config.header['Authorization'] = token
    } else if (!noAuthPaths.some((p) => config.url.includes(p))) {
      return Promise.reject(config)
    }
```

- [ ] **Step 2: 真机验证（Task 12 合并执行）**

Expected：启用前调 `/clinician/enable` 不被拦截；启用后带 `Authorization: Bearer ...` 命中受保护接口。

- [ ] **Step 3: 提交**

```bash
git add 蓝牙uniapp/utils/request.js
git commit -m "feat(app): request 改读 auth.getToken 并放行 clinician 启用/登录（对齐 §10）"
```

---

### Task 6: operatorStore 走后端启用/登录 + terminal_code（§1/§2/§3）

**Files:**
- Modify: `蓝牙uniapp/store/modules/operator.js`
- Modify: `蓝牙uniapp/utils/clinicStorage.js`（operator 增 token/terminal_code/clinicianId 字段，结构不破坏旧 API）

- [ ] **Step 1: clinicStorage 注释更新（结构说明）**

把 `utils/clinicStorage.js:2` 的注释：

```js
const OPERATOR_KEY = '__operator__'   // { hospital, dept, name, phone, passcode, enabled }
```

改为：

```js
const OPERATOR_KEY = '__operator__'   // { hospital, dept, name, phone, passcode, enabled, clinicianId, terminalCode }
```

- [ ] **Step 2: 重写 `store/modules/operator.js`**

```js
import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'
import { getTerminalCode } from '@/utils/terminal'
import { setToken, getToken } from '@/utils/auth'
import { clinicianEnableApi, clinicianLoginApi } from '@/api'

export const useOperatorStore = defineStore('operatorStore', {
  state: () => ({
    operator: getOperator() || null, // { hospital, dept, name, phone, passcode, enabled, clinicianId, terminalCode }
    unlocked: false
  }),
  getters: {
    isEnabled: (s) => !!(s.operator && s.operator.enabled)
  },
  actions: {
    // 首次启用：生成 terminal_code → POST /clinician/enable → 存 token + 本地档案
    async enable({ hospital, dept, name, phone, passcode }) {
      const terminalCode = getTerminalCode()
      const res = await clinicianEnableApi({
        hospital, dept, name, phone, terminal_code: terminalCode, passcode
      })
      setToken(`Bearer ${res.token}`)
      this.operator = {
        hospital, dept, name, phone, passcode, enabled: true,
        clinicianId: res.clinician.id, terminalCode
      }
      setOperator(this.operator)
      this.unlocked = true
      return res
    },
    // 本地解锁（离线可用，纯本地比对，保留）
    unlock(passcode) {
      if (this.operator && passcode === this.operator.passcode) {
        this.unlocked = true
        return true
      }
      return false
    },
    // 静默换 token：用本地 phone+terminalCode+passcode 调 /clinician/login，不弹登录页
    async refreshToken() {
      const o = this.operator
      if (!o || !o.passcode) throw new Error('未启用，无法刷新 token')
      const res = await clinicianLoginApi({
        phone: o.phone, terminal_code: o.terminalCode || getTerminalCode(), passcode: o.passcode
      })
      setToken(`Bearer ${res.token}`)
      this.operator = { ...o, clinicianId: res.clinician.id }
      setOperator(this.operator)
      return res
    },
    hasToken() { return !!getToken() },
    reset() {
      this.operator = null
      this.unlocked = false
      clearOperator()
    },
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

- [ ] **Step 3: 改 `pages/setup/enable.vue` 的 onEnable 为 async + 网络失败提示（§2 注意项）**

把 `pages/setup/enable.vue:24-30` 的 `onEnable`：

```js
function onEnable() {
  if (!f.hospital || !f.dept || !f.name) return uni.showToast({ title: '请填写医院/科室/姓名', icon: 'none' })
  if (!isValidPhone(f.phone)) return uni.showToast({ title: '请输入正确手机号', icon: 'none' })
  if (!f.passcode || f.passcode.length < 4) return uni.showToast({ title: '口令至少 4 位', icon: 'none' })
  op.enable({ ...f })
  uni.reLaunch({ url: '/pages/patient/select' })
}
```

替换为：

```js
async function onEnable() {
  if (!f.hospital || !f.dept || !f.name) return uni.showToast({ title: '请填写医院/科室/姓名', icon: 'none' })
  if (!isValidPhone(f.phone)) return uni.showToast({ title: '请输入正确手机号', icon: 'none' })
  if (!f.passcode || f.passcode.length < 4) return uni.showToast({ title: '口令至少 4 位', icon: 'none' })
  uni.showLoading({ title: '启用中', mask: true })
  try {
    await op.enable({ ...f })
    uni.hideLoading()
    uni.reLaunch({ url: '/pages/patient/select' })
  } catch (e) {
    uni.hideLoading()
    uni.showToast({ title: '启用失败：请检查网络后重试', icon: 'none', duration: 2500 })
  }
}
```

- [ ] **Step 4: 真机验证（Task 12 合并执行）**

Expected：首启填表 → 启用成功 → 本地 `__token__` 有 `Bearer ...`、`__operator__` 含 `clinicianId/terminalCode`；断网启用 → 提示「启用失败：请检查网络」。

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/store/modules/operator.js 蓝牙uniapp/utils/clinicStorage.js 蓝牙uniapp/pages/setup/enable.vue
git commit -m "feat(app): 启用/登录走后端，生成并上报 terminal_code（对齐 §1/§2/§3）"
```

---

### Task 7: 401 静默刷新 token 并重试（§3）

**Files:**
- Modify: `蓝牙uniapp/utils/request.js`（响应拦截器 401 分支）

> 思路：luch-request 响应失败时进入 reject。对 401 且非 enable/login/已重试的请求，调 `operatorStore.refreshToken()` 拿新 token，改写 header 重发一次。用 `config._retried` 防死循环。**不弹登录页、不清本地数据**（沿用现策略）。

- [ ] **Step 1: 在 `utils/request.js` 顶部加可复用的重试器**

在 import 区追加：

```js
import { useOperatorStoreWithOut } from '@/store/modules/operator'
```

在 `const instance = new Request({...})` 之后、`instance.interceptors.request.use` 之前，加：

```js
// 401 静默刷新并重试一次：用本地 phone+terminalCode+passcode 换新 token
async function retryWithRefresh(config) {
  if (config._retried) return Promise.reject(config)
  if (['/clinician/enable', '/clinician/login'].some((p) => config.url.includes(p))) {
    return Promise.reject(config)
  }
  const op = useOperatorStoreWithOut()
  if (!op.operator || !op.operator.passcode) return Promise.reject(config)
  await op.refreshToken()
  config._retried = true
  config.header = { ...(config.header || {}), Authorization: getToken() }
  return instance.request(config)
}
```

- [ ] **Step 2: 把响应成功拦截器里的 `code === 401` 分支接上重试**

把现 `utils/request.js:135-142`：

```js
    if (code === 401) {
      uni.showToast({
        icon: 'none',
        title: '鉴权失败',
        duration: 2000
      })
      return Promise.reject(response)
    }
```

替换为：

```js
    if (code === 401) {
      // 静默刷新换 token 重试一次（不弹登录页、不清本地数据）
      return retryWithRefresh(response.config).catch(() => {
        uni.showToast({ icon: 'none', title: '鉴权失败，请重新解锁', duration: 2000 })
        return Promise.reject(response)
      })
    }
```

把响应失败拦截器里的 `[401].includes(error?.data?.code)` 分支（现 `utils/request.js:184-189`）：

```js
    } else if ([401].includes(error?.data?.code)) {
      uni.showToast({
        icon: 'none',
        title: '鉴权失败',
        duration: 2000
      })
    } else {
```

替换为：

```js
    } else if ([401].includes(error?.data?.code) || error?.statusCode === 401) {
      return retryWithRefresh(error.config).catch(() => {
        uni.showToast({ icon: 'none', title: '鉴权失败，请重新解锁', duration: 2000 })
        return Promise.reject(error)
      })
    } else {
```

- [ ] **Step 3: 真机验证（Task 12 合并执行）**

Expected：手动让 token 过期（或后端缩短有效期）后调受保护接口 → App 自动换 token 重试成功、无登录页弹出、本地患者数据不丢。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp/utils/request.js
git commit -m "feat(app): 401 静默刷新 token 重试一次，不强制登出（对齐 §3）"
```

---

## Phase 2 — 患者流程（后端发 id/subject_id）

### Task 8: patientStore 后端驱动（§4）

**Files:**
- Modify: `蓝牙uniapp/store/modules/patient.js`
- Modify: `蓝牙uniapp/utils/clinicStorage.js`（当前患者键由 seq 改存 id；保留患者列表缓存）

- [ ] **Step 1: clinicStorage 当前患者键改存 id**

把 `utils/clinicStorage.js` 的 `getCurrentSeq/setCurrentSeq/clearCurrentSeq` 三个函数整体替换为（键名与语义改为 patientId）：

```js
const CURRENT_KEY  = '__current_patient_id__' // 后端 patient_id

export function getCurrentPatientId() {
  try { return uni.getStorageSync(CURRENT_KEY) || null } catch (e) { return null }
}
export function setCurrentPatientId(id) { uni.setStorageSync(CURRENT_KEY, id) }
export function clearCurrentPatientId() { uni.removeStorageSync(CURRENT_KEY) }
```

并删除文件顶部 `const CURRENT_KEY = '__current_patient__'` 旧行（避免重复声明）。

- [ ] **Step 2: 重写 `store/modules/patient.js`**

```js
import { defineStore } from 'pinia'
import { store } from '@/store'
import { getPatients, setPatients, getCurrentPatientId, setCurrentPatientId, clearCurrentPatientId } from '@/utils/clinicStorage'
import { searchPatients } from '@/utils/patient'
import { normalizePatient } from '@/utils/apiShape'
import { createPatientApi, listPatientsApi } from '@/api'

export const usePatientStore = defineStore('patientStore', {
  state: () => ({
    patients: getPatients() || [],          // 后端患者的本地缓存（离线展示用）
    currentId: getCurrentPatientId() || null // 后端 patient_id
  }),
  getters: {
    current: (s) => s.patients.find((p) => p.id === s.currentId) || null,
    // 当前患者编号 = 后端 subjectId（如 #00427）
    currentSubjectId: (s) => {
      const p = s.patients.find((x) => x.id === s.currentId)
      return p ? p.subjectId : ''
    }
  },
  actions: {
    // 新建患者：POST /patients，用后端返回的 id/subject_id；命中查重则提示已选中
    async create({ name, phone, gender, age }) {
      const res = await createPatientApi({ name, phone, gender, age })
      const p = normalizePatient(res)
      const idx = this.patients.findIndex((x) => x.id === p.id)
      if (idx >= 0) this.patients.splice(idx, 1)
      this.patients = [p, ...this.patients]
      setPatients(this.patients)
      this.select(p.id)
      return p // p.existed 标记是否为查重命中
    },
    // 拉取当前医护患者列表（权威以后端为准，写入本地缓存）
    async loadList() {
      const res = await listPatientsApi()
      this.patients = (res || []).map(normalizePatient)
      setPatients(this.patients)
      return this.patients
    },
    select(id) {
      this.currentId = id
      setCurrentPatientId(id)
    },
    clearCurrent() {
      this.currentId = null
      clearCurrentPatientId()
    },
    // 本地缓存按 lastAt 倒序 + 关键字过滤（离线展示）
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

> 注意：`CaPatientBar.vue` 引用 `ps.currentId`（旧为 subjectId 字符串）。现 `currentId` 改为后端数字 id，编号 getter 改名 `currentSubjectId`。**Task 10 会同步改 CaPatientBar**。

- [ ] **Step 3: 真机验证（Task 12 合并执行）**

Expected：新建患者后 `__current_patient_id__` 存数字 id、`__patients__` 缓存含 `subjectId`；查重（同号再建）返回既有患者并被选中。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp/store/modules/patient.js 蓝牙uniapp/utils/clinicStorage.js
git commit -m "feat(app): 患者改由后端发 id/subject_id，列表走 GET /patients（对齐 §4）"
```

---

### Task 9: 患者页接后端（new.vue / select.vue）（§4）

**Files:**
- Modify: `蓝牙uniapp/pages/patient/new.vue`
- Modify: `蓝牙uniapp/pages/patient/select.vue`

- [ ] **Step 1: 改 `pages/patient/new.vue`——去掉创建前编号预览，create 改 async + 查重提示**

把 `<script setup>`（`new.vue:24-37`）整体替换为：

```js
import { reactive } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { validatePatient } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const f = reactive({ name: '', phone: '', gender: '', age: '' })
async function onCreate() {
  const v = validatePatient(f)
  if (!v.ok) return uni.showToast({ title: v.msg, icon: 'none' })
  uni.showLoading({ title: '创建中', mask: true })
  try {
    const p = await ps.create({ ...f })
    uni.hideLoading()
    if (p.existed) uni.showToast({ title: '该患者已存在，已为你选中', icon: 'none', duration: 2000 })
    uni.switchTab({ url: '/pages/home/home' })
  } catch (e) {
    uni.hideLoading()
    uni.showToast({ title: '创建失败：请检查网络', icon: 'none' })
  }
}
```

把模板里「患者编号 自动生成」一行（`new.vue:17-18`）替换为（编号改由后端创建后产生，创建前不预览）：

```html
    <view class="lab">患者编号</view>
    <view class="idrow"><text class="idtag">创建后由系统自动派发</text><text class="idnote">导出科研只用此编号</text></view>
```

- [ ] **Step 2: 改 `pages/patient/select.vue`——onShow 拉后端列表，用 id/subjectId**

把 `<script setup>`（`select.vue:29-50`）整体替换为：

```js
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { maskPhone } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const kw = ref('')
const all = computed(() => ps.patients)
const list = computed(() => ps.list(kw.value))
const mask = maskPhone
function fmtDate(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function goNew() { uni.navigateTo({ url: '/pages/patient/new' }) }
function onPick(id) {
  ps.select(id)
  uni.switchTab({ url: '/pages/home/home' })
}
onShow(() => { ps.loadList().catch(() => { /* 离线：用本地缓存展示 */ }) })
```

把模板循环（`select.vue:18-25`）替换为（key/选择用 `p.id`，编号用 `p.subjectId`）：

```html
    <view v-for="p in list" :key="p.id" class="pcell" @tap="onPick(p.id)">
      <view class="av">{{ p.name.slice(0,1) }}</view>
      <view class="info">
        <view class="nm">{{ p.name }} <text class="ph">{{ mask(p.phone) }}</text></view>
        <view class="meta">{{ p.subjectId }} · 最近 {{ fmtDate(p.lastAt) }}</view>
      </view>
      <text class="arr">›</text>
    </view>
```

- [ ] **Step 3: 真机验证（Task 12 合并执行）**

Expected：进入选择页自动拉后端列表；点患者设为当前；离线时显示本地缓存不报错。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp/pages/patient/new.vue 蓝牙uniapp/pages/patient/select.vue
git commit -m "feat(app): 患者新建/选择接后端，编号改后端派发（对齐 §4）"
```

---

## Phase 3 — 采集补 patient_id + 按患者历史

### Task 10: 采集上传补 patient_id + 无患者禁采 + CaPatientBar 适配（§5）

**Files:**
- Modify: `蓝牙uniapp/store/modules/blueTooth.js`（import + 上传回调 `:246`）
- Modify: `蓝牙uniapp/components/base/CaPatientBar.vue`（`currentId`→`currentSubjectId`）

- [ ] **Step 1: blueTooth.js 换上传 API + 组装 payload + 无患者禁采**

把 `store/modules/blueTooth.js:3` 的 import：

```js
import { getUserDeviceListApi, sendDeviceRawDataApi, addUserDeviceListApi, updateDeviceApi, deleteDeviceApi } from '@/api'
```

替换为：

```js
import { listDevicesApi, registerDeviceApi, deleteDeviceApi as deleteDeviceApiReq, uploadRawDataApi } from '@/api'
import { buildRawDataPayload } from '@/utils/apiShape'
import { usePatientStoreWithOut } from '@/store/modules/patient'
```

把上传回调（`blueTooth.js:246`）：

```js
              sendDeviceRawDataApi(device.device_code,apiData)
```

替换为：

```js
              const ps = usePatientStoreWithOut()
              const patientId = ps.currentId
              if (!patientId) {
                // 无当前患者：禁止上传（避免数据无法归属）
                console.warn('未选择患者，已跳过本帧上传')
                return
              }
              uploadRawDataApi(device.device_code, buildRawDataPayload(patientId, apiData))
```

把 `getDevicesList`（`blueTooth.js:302`）里的 `getUserDeviceListApi()` 改为 `listDevicesApi()`；
把 `addDevice`（`blueTooth.js:362`）里的 `addUserDeviceListApi(deviceObj)` 改为 `registerDeviceApi(deviceObj)`；
把 `deleteDevice`（`blueTooth.js:385`）里的 `deleteDeviceApi(id)` 改为 `deleteDeviceApiReq(id)`。

> `addDevice` 传入的 `deviceObj` 含 `{device_name, device_code, is_active, frequency}`；后端只取 `device_code`、`device_name`，多余字段忽略（spec §5「其余字段后端先忽略」同理），无需删。`updateDevice`/`updateDeviceApi` 在新后端无对应接口——**保留为空操作或在 Task 11 一并删除其调用**（现仅旧逻辑引用，见 Task 11）。

- [ ] **Step 2: CaPatientBar 编号字段改名**

把 `components/base/CaPatientBar.vue:21` 的 `ps.currentId`：

```js
  return [ps.currentId, p.gender, p.age ? p.age + '岁' : ''].filter(Boolean).join(' · ')
```

替换为：

```js
  return [ps.currentSubjectId, p.gender, p.age ? p.age + '岁' : ''].filter(Boolean).join(' · ')
```

- [ ] **Step 3: 真机验证（Task 12 合并执行）**

Expected：选患者→蓝牙连接→上传带 `patient_id`，后端 `device_raw_data` 落库归属正确；未选患者时不产生上传。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp/store/modules/blueTooth.js 蓝牙uniapp/components/base/CaPatientBar.vue
git commit -m "feat(app): 采集上传补 patient_id，无当前患者禁采（对齐 §5）"
```

---

### Task 11: 数据页按患者拉历史 + 删除旧接口（§7/§8）

**Files:**
- Modify: `蓝牙uniapp/pages/data/data.vue`
- Modify: `蓝牙uniapp/store/modules/blueTooth.js`（移除 `updateDevice`/`updateDeviceApi` 残留引用，若有）
- Delete content: `蓝牙uniapp/api/user.js`（删除作废接口）
- Modify: `蓝牙uniapp/api/index.js`（移除 `export * from './user'`）

- [ ] **Step 1: data.vue 拉 `/patients/<id>/data` 驱动 hasData**

把 `pages/data/data.vue` 的 `<script setup>` 顶部（`data.vue:36-44`）：

```js
import { ref, computed } from 'vue'
import { getBarOpts } from '@/utils/ucharts'

const ranges = ['本周', '上周', '本月', '近半年']
const range = ref(0)

// 真实数据接入前：默认有示意数据；接入后用「该时间段是否有该患者数据」驱动
const hasData = ref(true)
```

替换为：

```js
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getBarOpts } from '@/utils/ucharts'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { getPatientHistoryApi } from '@/api'
import { mapHistoryItem } from '@/utils/apiShape'

const ps = usePatientStoreWithOut()
const ranges = ['本周', '上周', '本月', '近半年']
const range = ref(0)

const history = ref([])
const hasData = computed(() => history.value.length > 0)

async function loadHistory() {
  const id = ps.currentId
  if (!id) { history.value = []; return }
  try {
    const res = await getPatientHistoryApi(id, { page: 1, page_size: 200 })
    history.value = (res?.items || []).map(mapHistoryItem)
  } catch (e) {
    history.value = [] // 离线/越权：走空态
  }
}
onShow(loadHistory)
```

> 说明：本任务**只接通「有无该患者数据 → 空态/内容」**与历史拉取；KPI/趋势图的真实聚合（从 6 轴/T 值算步态指标）依赖后续分析 spec，暂沿用现有示意 `lineData/pressureData/singleData`，不在本对齐范围内扩展（YAGNI）。`history.value` 已就位，后续接图时直接用。

- [ ] **Step 2: 清理 blueTooth.js 里 updateDevice 残留（如存在）**

确认 `store/modules/blueTooth.js` 不再 import/调用 `updateDeviceApi`。若 `updateDevice` action 仅被旧逻辑引用且无页面调用，删除该 action 及其 import。用：

Run: `cd 蓝牙uniapp && npx vitest run`（确保纯函数测试仍绿）+ 全局检索 `updateDeviceApi`/`updateDevice(` 无残留引用。

- [ ] **Step 3: 删除 `api/user.js` 作废接口**

`api/user.js` 全部函数对应旧后端，scope A 已被 clinician/patient/device 取代——删除整个文件内容，替换为空导出占位（或直接删文件并移除 index 导出）。采用删文件：

删除 `蓝牙uniapp/api/user.js`，并把 `api/index.js` 改回：

```js
export * from './clinician'
export * from './patient'
export * from './device'
```

- [ ] **Step 4: 全局确认无旧接口引用**

Run（确保无残留 import）：检索 `from '@/api/user'`、`userLoginApi`、`userRegisterApi`、`getUserWeekPlanApi`、`getDeviceDataApi`、`getUserDeviceListApi`、`addUserDeviceListApi`、`sendDeviceRawDataApi`、`getDeviceLatestT1T2Api`、`getUserT2T3Api`、`getDeviceDailyAveragesApi`、`userAvatarUploadApi`、`userUpdateApi` 在 `蓝牙uniapp/` 下命中应为 0（`store/modules/user.js` 若仍 import 旧接口，一并处理：该 store 为旧登录模型遗留且无页面调用，删除其 `userLoginApi/userUpdateApi` 依赖或删除整个 `user.js` store 与 `store/index.js` 中的引用）。

Expected：检索结果为空；`npx vitest run` 全绿。

- [ ] **Step 5: 提交**

```bash
git add 蓝牙uniapp/pages/data/data.vue 蓝牙uniapp/store/modules/blueTooth.js 蓝牙uniapp/api/index.js
git rm 蓝牙uniapp/api/user.js
git commit -m "feat(app): 数据页按患者拉历史，删除作废旧接口（对齐 §7/§8）"
```

---

## Phase 4 — 真机回归与收尾

### Task 12: 真机全流程回归（HBuilderX → 真后端）

**Files:** 无代码改动（仅验证 + 必要修补）

> 前端 store/页面/蓝牙/网络无法用 vitest mock，统一在此对真后端（`http://118.31.39.47`，先 HTTP）真机回归。逐项勾验收。

- [ ] **Step 1: 纯函数回归**

Run: `cd 蓝牙uniapp && npx vitest run`
Expected: PASS（patient/terminal/apiShape 全绿）

- [ ] **Step 2: 真机手动验收（HBuilderX 运行到 Android 真机）**

逐项确认：
- [ ] 首启 → 填医院/科室/医生/手机/口令 → 启用成功；本地有 `__token__`(`Bearer ...`)、`__operator__`(含 `clinicianId/terminalCode`)、`__terminal_code__`。
- [ ] 断网启用 → 提示「启用失败：请检查网络」，不崩。
- [ ] 杀进程重开 → 解锁页输口令 → 进入；离线也能解锁（本地比对）。
- [ ] 选择患者页自动拉后端列表；新建患者 → 编号由后端返回（创建前不预览）；同手机号再建 → 提示「该患者已存在，已为你选中」。
- [ ] 我的页扫码加设备 → 列表出现；连接成功后采集 → 后端 `device_raw_data` 落库且 `patient_id/clinician_id/device_id` 归属正确。
- [ ] 未选患者时连接采集 → 不产生上传（日志「未选择患者，已跳过」）。
- [ ] 数据页：有该患者历史 → 退出示意空态、`history` 有数据；无历史 → 空态。
- [ ] token 过期（可临时调小后端有效期）→ 受保护接口自动静默换 token 重试，不弹登录页、本地患者列表不丢。
- [ ] 删除设备（限本医护）正常；跨医护数据互不可见（换一台启用不同手机号验证 403/空）。

- [ ] **Step 3: 更新 CLAUDE.md 与系统架构方案进展（硬性要求 §3.3）**

在 `DataCollectionApp/CLAUDE.md` 阶段 1「待办」与 2.1「仍待办」中，把「App 端接入新接口」标记为已完成（或剩余项），记录本次对齐落地。

- [ ] **Step 4: 提交**

```bash
git add 蓝牙uniapp DataCollectionApp/CLAUDE.md
git commit -m "docs: 前后端对齐真机回归通过，更新进展（对齐 §1-§8 收尾）"
```

---

## 自检（对照 spec 复核）

**1. spec 覆盖**
- §1 terminal_code → Task 1 + Task 6 ✓
- §2 enable → Task 4 + Task 6 ✓
- §3 login/解锁/401 刷新 → Task 6 + Task 7（本地 unlock 保留）✓
- §4 患者 subject_id/查重/列表 → Task 2/3/8/9 ✓
- §5 上传补 patient_id/无患者禁采 → Task 2 + Task 10 ✓
- §6 设备 → 已对齐，沿用扫码加设备（spec §11.3-3）；API 换模块在 Task 4/10 ✓
- §7 按患者历史 → Task 2 + Task 11 ✓
- §8 旧接口清理 → Task 4（并存）→ Task 11（删除）✓
- §9 字段映射 → Task 2（normalizePatient）+ Task 6/8 ✓
- §10 不变项 → Task 5（token/白名单）保留包络与不强制登出 ✓

**2. 占位符扫描**：无 TBD/“稍后实现”；每步含可执行代码或命令。KPI 图真实聚合明确划出范围（依赖后续分析 spec），非占位。

**3. 类型一致性**：患者前端形状 `{id, subjectId, name, phone, gender, age, lastAt, existed}` 在 Task 2 定义，Task 8/9/10/11 一致引用；`currentId`(数字 id) 与 `currentSubjectId`(编号串) 命名在 Task 8 定义、Task 10 CaPatientBar 同步；token 整串 `"Bearer xxx"` 在 Task 6 产生、Task 5/7 消费一致。

---

## Execution Handoff

Plan 已保存到 `docs/superpowers/plans/2026-06-07-frontend-backend-alignment.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个任务派新子 agent，任务间评审，迭代快。
2. **Inline Execution** — 本会话内分批执行 + 检查点。

> 注意：Phase 0 的纯函数任务可子 agent TDD；Phase 1-4 的接线任务无法 vitest 验证，子 agent 完成代码后需在 Task 12 由人真机回归——执行时请把「真机验收」留给用户手动跑。
