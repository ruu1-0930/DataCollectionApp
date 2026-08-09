import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOperator } from '../utils/clinicStorage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('operator profile storage hydration', () => {
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
