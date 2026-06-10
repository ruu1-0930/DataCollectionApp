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

// 设备步长发的是米；显示用厘米。非数值/null/undefined 返回 NaN（上层 fmt 会显示 '-'）。
export function mToCm(m) {
  if (m == null) return NaN
  const n = Number(m)
  return Number.isFinite(n) ? n * 100 : NaN
}
