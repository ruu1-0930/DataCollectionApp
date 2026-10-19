import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { assertCollectionIdentity } from '../utils/collectionSession'

describe('actual request interceptor collection owner fence', () => {
  let instance, op, sends, token
  const config = () => ({ url: '/collection-sessions', method: 'post', header: {}, custom: {
    collectionIdentity: { clinicianId: 11, authEpoch: 1 },
  } })
  beforeEach(() => {
    sends = []
    token = 'Bearer clinician-11'
    op = { operator: { clinicianId: 11 }, runtimePasscode: 'synthetic', unlocked: true, authRuntime: { authEpoch: 1 }, refreshToken: async () => {} }
    globalThis.uni = { showToast: vi.fn() }
    class Request {
      constructor() {
        this.interceptors = { request: { use: (success, failure) => { this.before = success; this.beforeError = failure } },
          response: { use: (success, failure) => { this.response = success; this.failure = failure } } }
      }
      async request(value) { const checked = await this.before(value); sends.push(checked); return checked }
    }
    const source = readFileSync(new URL('../utils/request.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export \{ instance \}/, '')
    instance = new Function('Request', 'baseURL', 'requestTimeout', 'contentType', 'getToken', 'useOperatorStoreWithOut',
      'logRequestError', 'logRequestStart', 'logResponse', 'assertCollectionIdentity', source + '\nreturn instance;')(
      Request, 'https://synthetic.invalid', 30000, 'application/json', () => token, () => op, () => {}, () => {}, () => {}, assertCollectionIdentity)
  })
  it('unwraps the real Response envelope to the exact collection receipt', async () => {
    expect(await instance.response({ config: config(), data: { code: 200, data: { capture_id: 'capture' } } })).toEqual({ capture_id: 'capture' })
  })
  it('checks owner before binding a token to an actual request', async () => {
    op.operator.clinicianId = 12
    token = 'Bearer clinician-12'
    await expect(instance.request(config())).rejects.toThrow('collection_identity_changed')
    expect(sends).toEqual([])
  })
  it('does not refresh an old collection under a new authentication epoch', async () => {
    let refreshes = 0
    op.refreshToken = async () => { refreshes++ }
    op.authRuntime.authEpoch = 2
    await expect(instance.failure({ statusCode: 401, config: config() })).rejects.toBeTruthy()
    expect(refreshes).toBe(0)
    expect(sends).toEqual([])
  })
  it('rechecks identity after a refresh before resending with a new JWT', async () => {
    op.refreshToken = async () => { op.operator.clinicianId = 12; op.authRuntime.authEpoch = 2; token = 'Bearer clinician-12' }
    await expect(instance.response({ config: config(), data: { code: 401 } })).rejects.toBeTruthy()
    expect(sends).toEqual([])
  })
  it('refreshes once for the same owner and preserves collection metadata', async () => {
    op.refreshToken = async () => { token = 'Bearer refreshed-11' }
    await instance.failure({ statusCode: 401, config: config() })
    expect(sends).toHaveLength(1)
    expect(sends[0].header.Authorization).toBe('Bearer refreshed-11')
    expect(sends[0].custom.collectionIdentity).toEqual({ clinicianId: 11, authEpoch: 1 })
    expect(sends[0].custom._retried).toBe(true)
  })
})
