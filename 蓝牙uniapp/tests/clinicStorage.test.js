import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOperator } from '../utils/clinicStorage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('operator profile storage hydration', () => {
  it('returns the same clean operator profile without rewriting storage', () => {
    const storedOperator = {
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
      passcode: '1234',
      enabled: true,
      clinicianId: 27,
    }
    const getStorageSync = vi.fn(() => storedOperator)
    const setStorageSync = vi.fn()
    vi.stubGlobal('uni', { getStorageSync, setStorageSync })

    expect(getOperator()).toBe(storedOperator)
    expect(setStorageSync).not.toHaveBeenCalled()
  })

  it('preserves a near-miss key without rewriting storage', () => {
    const storedOperator = {
      hospital: '协和医院',
      name: '王医生',
      terminalCod: 'near-miss',
    }
    const getStorageSync = vi.fn(() => storedOperator)
    const setStorageSync = vi.fn()
    vi.stubGlobal('uni', { getStorageSync, setStorageSync })

    const hydrated = getOperator()
    expect(hydrated).toBe(storedOperator)
    expect(hydrated).toHaveProperty('terminalCod', 'near-miss')
    expect(setStorageSync).not.toHaveBeenCalled()
  })

  it('removes legacy terminal identity and immediately rewrites every other field', () => {
    const storedOperator = {
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
      passcode: '1234',
      enabled: true,
      clinicianId: 27,
      preferences: { locale: 'zh-CN' },
      terminalCode: 'legacy-terminal',
    }
    const expectedOperator = {
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
      passcode: '1234',
      enabled: true,
      clinicianId: 27,
      preferences: { locale: 'zh-CN' },
    }
    const getStorageSync = vi.fn(() => storedOperator)
    const setStorageSync = vi.fn()
    vi.stubGlobal('uni', { getStorageSync, setStorageSync })

    expect(getOperator()).toEqual(expectedOperator)
    expect(getStorageSync).toHaveBeenCalledWith('__operator__')
    expect(setStorageSync).toHaveBeenCalledOnce()
    expect(setStorageSync).toHaveBeenCalledWith('__operator__', expectedOperator)
  })
})
