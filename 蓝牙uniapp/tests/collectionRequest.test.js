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
  it('preserves independent radar events and their fixed owner through the real interceptor', async () => {
    const request = config()
    request.url = '/collection-sessions/capture/batches'
    request.data = { events: [{ event_id: 'radar-event', stream: 'radar', connection_epoch: 3, stream_sequence: 0, payload: { frames: 1, bytes: 30, age_ms: 1, stale: false, targets: [] } }] }
    await instance.request(request)
    expect(sends[0].data).toEqual(request.data)
    expect(sends[0].custom.collectionIdentity).toEqual({ clinicianId: 11, authEpoch: 1 })
  })
  it('sends registered create and final-count stop to V2 without changing batch and legacy paths', async () => {
    const source = readFileSync(new URL('../api/device.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
    const api = new Function('instance', source + '\nreturn { createCollectionApi, uploadCollectionBatchApi, stopCollectionApi };')({
      request: value => instance.request({ ...value, header: {} }),
    })
    const owner = config().custom.collectionIdentity
    const registration = { schema_version: 1, patient_id: 7, test_type: 'tug' }
    const counts = { insole: 2, gps: 0, radar: 5 }
    await api.createCollectionApi({ capture_id: 'capture' }, owner)
    await api.createCollectionApi({ capture_id: 'capture', schema_version: 2, registration }, owner)
    await api.uploadCollectionBatchApi('capture', { events: [] }, owner)
    await api.stopCollectionApi('capture', { mobile_stopped_at: '2026-10-23T00:00:00.000Z' }, owner)
    await api.stopCollectionApi('capture', { schema_version: 2, final_counts: counts }, owner)
    expect(sends.map(r => r.url)).toEqual(['/collection-sessions', '/v2/collection-sessions', '/collection-sessions/capture/batches',
      '/collection-sessions/capture/stop', '/v2/collection-sessions/capture/stop'])
    expect(sends[1].data.registration).toEqual(registration)
    expect(sends[4].data.final_counts).toEqual(counts)
    expect(sends.every(r => r.custom.collectionIdentity === owner)).toBe(true)
  })
  it('uses the actual V2 patient create, profile read and profile replacement URLs', async () => {
    const source = readFileSync(new URL('../api/patient.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
    const api = new Function('instance', source + '\nreturn { createPatientApi, getPatientProfileApi, savePatientProfileApi };')({
      request: value => instance.request({ ...value, header: {}, custom: value.custom || {} }),
    })
    const profile = { name: '合成患者', phone: null, gender: '男', age: 60, height_cm: 170, weight_kg: 65, shoe_size_eu: 40.5 }
    await api.createPatientApi(profile)
    await api.getPatientProfileApi(7, config().custom)
    await api.savePatientProfileApi(7, profile, config().custom)
    expect(sends.map(r => [r.method, r.url])).toEqual([['post', '/v2/patients'], ['get', '/v2/patients/7/profile'], ['put', '/v2/patients/7/profile']])
    expect(sends[0].data).toEqual(profile)
    expect(sends[2].data).toEqual(profile)
    op.authRuntime.authEpoch = 2
    await expect(api.savePatientProfileApi(7, profile, config().custom)).rejects.toThrow('collection_identity_changed')
    expect(sends).toHaveLength(3)
  })
  it('carries the create patient owner and prevents an old 401 refresh under a new epoch', async () => {
    const source = readFileSync(new URL('../api/patient.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
    const api = new Function('instance', source + '\nreturn { createPatientApi };')({
      request: value => instance.request({ ...value, header: {}, custom: value.custom || {} }),
    })
    await api.createPatientApi({}, config().custom)
    const sent = sends[0]
    op.refreshToken = vi.fn(async () => {})
    op.operator.clinicianId = 12
    op.authRuntime.authEpoch = 2
    await expect(instance.failure({ statusCode: 401, config: sent })).rejects.toBeTruthy()
    expect(op.refreshToken).not.toHaveBeenCalled()
    expect(sends).toHaveLength(1)
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
