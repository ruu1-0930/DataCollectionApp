import { describe, expect, it, vi } from 'vitest'
import {
  authenticateOperator,
  buildPersistentOperator,
  createOperatorSessionRuntime,
  enableOperatorSession,
  refreshOperatorSession,
  resetOperatorSession,
  unlockOperatorSession,
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
    const runtime = createOperatorSessionRuntime()
    const clearOperator = vi.fn()
    const clearToken = vi.fn()

    resetOperatorSession({ state, runtime, clearOperator, clearToken })

    expect(state).toEqual({
      operator: null,
      runtimePasscode: null,
      unlocked: false,
    })
    expect(clearOperator).toHaveBeenCalledOnce()
    expect(clearToken).toHaveBeenCalledOnce()
  })

  it('does not restore credentials when reset wins over an in-flight refresh', async () => {
    const login = deferred()
    const state = {
      operator: profile,
      runtimePasscode: 'runtime-secret',
      unlocked: true,
    }
    const runtime = createOperatorSessionRuntime()
    const setToken = vi.fn()
    const setOperator = vi.fn()
    const clearOperator = vi.fn()
    const clearToken = vi.fn()

    const refresh = refreshOperatorSession({
      state,
      runtime,
      loginApi: () => login.promise,
      setToken,
      setOperator,
    })

    resetOperatorSession({ state, runtime, clearOperator, clearToken })
    login.resolve({ token: 'late-token', clinician: { id: 41 } })

    await expect(refresh).resolves.toBeNull()
    expect(state).toEqual({
      operator: null,
      runtimePasscode: null,
      unlocked: false,
    })
    expect(setToken).not.toHaveBeenCalled()
    expect(setOperator).not.toHaveBeenCalled()
    expect(clearOperator).toHaveBeenCalledOnce()
    expect(clearToken).toHaveBeenCalledOnce()
  })

  it('shares one in-flight refresh for concurrent 401 handlers and releases it afterward', async () => {
    const login = deferred()
    const state = {
      operator: profile,
      runtimePasscode: 'runtime-secret',
      unlocked: true,
    }
    const runtime = createOperatorSessionRuntime()
    const loginApi = vi.fn(() => login.promise)
    const setToken = vi.fn()
    const setOperator = vi.fn()

    const first = refreshOperatorSession({ state, runtime, loginApi, setToken, setOperator })
    const second = refreshOperatorSession({ state, runtime, loginApi, setToken, setOperator })

    expect(first).toBe(second)
    expect(loginApi).toHaveBeenCalledOnce()

    login.resolve({ token: 'renewed-token', clinician: { id: 41 } })

    await expect(Promise.all([first, second])).resolves.toEqual([
      {
        token: 'Bearer renewed-token',
        operator: { ...profile, clinicianId: 41 },
      },
      {
        token: 'Bearer renewed-token',
        operator: { ...profile, clinicianId: 41 },
      },
    ])
    expect(setToken).toHaveBeenCalledWith('Bearer renewed-token')
    expect(setOperator).toHaveBeenCalledWith({ ...profile, clinicianId: 41 })

    await expect(refreshOperatorSession({ state, runtime, loginApi, setToken, setOperator }))
      .resolves.toEqual({
        token: 'Bearer renewed-token',
        operator: { ...profile, clinicianId: 41 },
      })
    expect(loginApi).toHaveBeenCalledTimes(2)
  })

  it('releases a rejected refresh so a later 401 can retry', async () => {
    const firstLogin = deferred()
    const secondLogin = deferred()
    const state = {
      operator: profile,
      runtimePasscode: 'runtime-secret',
      unlocked: true,
    }
    const runtime = createOperatorSessionRuntime()
    const loginApi = vi
      .fn(() => firstLogin.promise)
      .mockImplementationOnce(() => firstLogin.promise)
      .mockImplementationOnce(() => secondLogin.promise)
    const setToken = vi.fn()
    const setOperator = vi.fn()

    const failedRefresh = refreshOperatorSession({
      state,
      runtime,
      loginApi,
      setToken,
      setOperator,
    })
    firstLogin.reject(new Error('unauthorized'))
    await expect(failedRefresh).rejects.toThrow('unauthorized')

    const retriedRefresh = refreshOperatorSession({
      state,
      runtime,
      loginApi,
      setToken,
      setOperator,
    })
    expect(loginApi).toHaveBeenCalledTimes(2)

    secondLogin.resolve({ token: 'retry-token', clinician: { id: 41 } })
    await expect(retriedRefresh).resolves.toEqual({
      token: 'Bearer retry-token',
      operator: { ...profile, clinicianId: 41 },
    })
  })

  it('prevents an old refresh from overwriting a replacement unlock', async () => {
    const oldRefreshLogin = deferred()
    const replacementLogin = deferred()
    const state = {
      operator: profile,
      runtimePasscode: 'old-secret',
      unlocked: true,
    }
    const runtime = createOperatorSessionRuntime()
    const setToken = vi.fn()
    const setOperator = vi.fn()

    const oldRefresh = refreshOperatorSession({
      state,
      runtime,
      loginApi: () => oldRefreshLogin.promise,
      setToken,
      setOperator,
    })
    const replacementUnlock = unlockOperatorSession({
      state,
      runtime,
      passcode: 'replacement-secret',
      loginApi: () => replacementLogin.promise,
      setToken,
      setOperator,
    })

    replacementLogin.resolve({ token: 'replacement-token', clinician: { id: 52 } })
    await expect(replacementUnlock).resolves.toBe(true)
    oldRefreshLogin.resolve({ token: 'stale-token', clinician: { id: 41 } })
    await expect(oldRefresh).resolves.toBeNull()

    expect(state).toEqual({
      operator: { ...profile, clinicianId: 52 },
      runtimePasscode: 'replacement-secret',
      unlocked: true,
    })
    expect(setToken).toHaveBeenCalledOnce()
    expect(setToken).toHaveBeenCalledWith('Bearer replacement-token')
    expect(setOperator).toHaveBeenCalledOnce()
    expect(setOperator).toHaveBeenCalledWith({ ...profile, clinicianId: 52 })
  })

  it('prevents an old refresh from overwriting a replacement enable', async () => {
    const oldRefreshLogin = deferred()
    const replacementEnable = deferred()
    const state = {
      operator: profile,
      runtimePasscode: 'old-secret',
      unlocked: true,
    }
    const runtime = createOperatorSessionRuntime()
    const setToken = vi.fn()
    const setOperator = vi.fn()
    const replacementCredentials = {
      hospital: '人民医院',
      dept: '康复科',
      name: '李医生',
      phone: '13900000000',
      passcode: 'replacement-secret',
    }

    const oldRefresh = refreshOperatorSession({
      state,
      runtime,
      loginApi: () => oldRefreshLogin.promise,
      setToken,
      setOperator,
    })
    const enabled = enableOperatorSession({
      state,
      runtime,
      credentials: replacementCredentials,
      enableApi: () => replacementEnable.promise,
      setToken,
      setOperator,
    })

    replacementEnable.resolve({ token: 'replacement-token', clinician: { id: 63 } })
    await expect(enabled).resolves.toEqual({
      token: 'replacement-token',
      clinician: { id: 63 },
    })
    oldRefreshLogin.resolve({ token: 'stale-token', clinician: { id: 41 } })
    await expect(oldRefresh).resolves.toBeNull()

    expect(state).toEqual({
      operator: {
        hospital: '人民医院',
        dept: '康复科',
        name: '李医生',
        phone: '13900000000',
        enabled: true,
        clinicianId: 63,
      },
      runtimePasscode: 'replacement-secret',
      unlocked: true,
    })
    expect(setToken).toHaveBeenCalledOnce()
    expect(setToken).toHaveBeenCalledWith('Bearer replacement-token')
    expect(setOperator).toHaveBeenCalledOnce()
    expect(setOperator).toHaveBeenCalledWith({
      hospital: '人民医院',
      dept: '康复科',
      name: '李医生',
      phone: '13900000000',
      enabled: true,
      clinicianId: 63,
    })
  })

  it('allows only the latest overlapping explicit authentication to commit', async () => {
    const firstLogin = deferred()
    const secondLogin = deferred()
    const state = {
      operator: profile,
      runtimePasscode: null,
      unlocked: false,
    }
    const runtime = createOperatorSessionRuntime()
    const setToken = vi.fn()
    const setOperator = vi.fn()

    const firstUnlock = unlockOperatorSession({
      state,
      runtime,
      passcode: 'first-secret',
      loginApi: () => firstLogin.promise,
      setToken,
      setOperator,
    })
    const secondUnlock = unlockOperatorSession({
      state,
      runtime,
      passcode: 'second-secret',
      loginApi: () => secondLogin.promise,
      setToken,
      setOperator,
    })

    secondLogin.resolve({ token: 'second-token', clinician: { id: 72 } })
    await expect(secondUnlock).resolves.toBe(true)
    firstLogin.resolve({ token: 'first-token', clinician: { id: 71 } })
    await expect(firstUnlock).resolves.toBe(false)

    expect(state).toEqual({
      operator: { ...profile, clinicianId: 72 },
      runtimePasscode: 'second-secret',
      unlocked: true,
    })
    expect(setToken).toHaveBeenCalledOnce()
    expect(setToken).toHaveBeenCalledWith('Bearer second-token')
    expect(setOperator).toHaveBeenCalledOnce()
    expect(setOperator).toHaveBeenCalledWith({ ...profile, clinicianId: 72 })
  })

  it('wires the Pinia store to asynchronous runtime authentication', () => {
    const source = readSource('../store/modules/operator.js')
    expect(source).toContain('runtimePasscode: null')
    expect(source).toContain('unlockOperatorSession')
    expect(source).toContain('enableOperatorSession')
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

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
