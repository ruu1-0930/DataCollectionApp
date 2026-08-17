import { describe, expect, it, vi } from 'vitest'
import {
  authenticateOperator,
  buildPersistentOperator,
  resetOperatorSession,
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

  it('resets runtime state and clears both the profile and persisted token', () => {
    const state = {
      operator: profile,
      runtimePasscode: 'runtime-secret',
      unlocked: true,
    }
    const clearOperator = vi.fn()
    const clearToken = vi.fn()

    resetOperatorSession({ state, clearOperator, clearToken })

    expect(state).toEqual({
      operator: null,
      runtimePasscode: null,
      unlocked: false,
    })
    expect(clearOperator).toHaveBeenCalledOnce()
    expect(clearToken).toHaveBeenCalledOnce()
  })

  it('wires the Pinia store to asynchronous runtime authentication', () => {
    const source = readSource('../store/modules/operator.js')
    expect(source).toContain('runtimePasscode: null')
    expect(source).toContain('async unlock(passcode)')
    expect(source).toContain('authenticateOperator')
    expect(source).toContain('resetOperatorSession')
  })

  it('connects the unlock page to the executable submission gate', () => {
    const source = readSource('../pages/setup/unlock.vue')
    expect(source).toContain('createSubmissionGate')
    expect(source).toContain(':class="{ disabled: submitting }"')
    expect(source).toContain("submitting ? '验证中…' : '解锁'")
  })
})

function readSource(relativePath) {
  return require('node:fs').readFileSync(
    new URL(relativePath, import.meta.url),
    'utf8',
  )
}
