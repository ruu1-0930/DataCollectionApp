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
