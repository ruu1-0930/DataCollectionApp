import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOperator, setOperator } from '../utils/clinicStorage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('operator profile storage hydration', () => {
  it('returns a clean operator profile without rewriting storage', () => {
    const storedOperator = {
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
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

  it('removes legacy passcode and terminal identity before immediately rewriting storage', () => {
    const storedOperator = {
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
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

  it('strips passcode and exact legacy terminalCode before writing an operator profile', () => {
    const setStorageSync = vi.fn()
    vi.stubGlobal('uni', { setStorageSync })

    setOperator({
      hospital: '协和医院',
      name: '王医生',
      passcode: '1234',
      terminalCode: 'legacy-terminal',
      enabled: true,
    })

    expect(setStorageSync).toHaveBeenCalledWith('__operator__', {
      hospital: '协和医院',
      name: '王医生',
      enabled: true,
    })
  })
})
