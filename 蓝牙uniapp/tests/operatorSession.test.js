import { describe, expect, it, vi } from 'vitest'
import {
  authenticateOperator,
  buildPersistentOperator,
} from '../utils/operatorSession'

const profile = {
  hospital: '协和医院',
  dept: '骨科',
  name: '王医生',
  phone: '13800000000',
  enabled: true,
  clinicianId: 27,
}

describe('operator runtime authentication', () => {
  it('builds a persistent profile without a passcode', () => {
    expect(buildPersistentOperator({ ...profile, passcode: '1234' }, { id: 41 })).toEqual({
      ...profile,
      clinicianId: 41,
    })
  })

  it('authenticates with the supplied runtime passcode and returns a sanitized profile', async () => {
    const loginApi = vi.fn().mockResolvedValue({
      token: 'new-token',
      clinician: { id: 41 },
    })

    await expect(authenticateOperator({
      operator: profile,
      passcode: 'runtime-secret',
      loginApi,
    })).resolves.toEqual({
      token: 'Bearer new-token',
      operator: { ...profile, clinicianId: 41 },
    })

    expect(loginApi).toHaveBeenCalledWith({
      hospital: '协和医院',
      name: '王医生',
      phone: '13800000000',
      passcode: 'runtime-secret',
    })
  })

  it('rejects a failed unlock without manufacturing a token or profile', async () => {
    const loginApi = vi.fn().mockRejectedValue(new Error('unauthorized'))

    await expect(authenticateOperator({
      operator: profile,
      passcode: 'wrong-secret',
      loginApi,
    })).rejects.toThrow('unauthorized')
  })

  it('refuses refresh when no runtime passcode is available', async () => {
    const loginApi = vi.fn()

    await expect(authenticateOperator({ operator: profile, passcode: '', loginApi }))
      .rejects.toThrow('运行期口令不可用')
    expect(loginApi).not.toHaveBeenCalled()
  })

  it('wires the Pinia store to asynchronous runtime authentication', () => {
    const source = readSource('../store/modules/operator.js')
    expect(source).toContain('runtimePasscode: null')
    expect(source).toContain('async unlock(passcode)')
    expect(source).toContain('authenticateOperator')
    expect(source).toContain('this.runtimePasscode = null')
  })

  it('awaits remote unlock in the unlock page', () => {
    const source = readSource('../pages/setup/unlock.vue')
    expect(source).toContain('async function onUnlock()')
    expect(source).toContain('await op.unlock(passcode.value)')
  })
})

function readSource(relativePath) {
  return require('node:fs').readFileSync(
    new URL(relativePath, import.meta.url),
    'utf8',
  )
}
