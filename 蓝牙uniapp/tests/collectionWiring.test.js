import { savedRegistration } from './helpers/savedRegistration'
import { collectionStopReceipt } from './helpers/collectionStopReceipt'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { createBleLines, parseTelemetry } from '../utils/bleTelemetry'
import { createCollectionSession } from '../utils/collectionSession'
import { createCollectionCoordinator } from '../utils/collectionCoordinator'
import { COLLECTION_TEST_TYPES, createRegistrationDraft } from '../utils/collectionRegistration'
import { createOperatorSessionRuntime, resetOperatorSession } from '../utils/operatorSession'
import { normalizePatient } from '../utils/apiShape'
import { normalizePatientProfile } from '../utils/patient'

// The UTS plugin and Pinia are supplied by HBuilderX, not this Node package.
// Execute the actual store actions with only those native/framework seams replaced.
function loadStore(dependencies) {
  let source = readFileSync(new URL('../store/modules/blueTooth.js', import.meta.url), 'utf8')
  source = source.replace(/^import .*$/gm, '').replace(/export /g, '')
  return new Function(...Object.keys(dependencies), source + '\nreturn useBlueToothStore();')(...Object.values(dependencies))
}
const bytes = (s) => Uint8Array.from([...s].map(c => c.charCodeAt(0))).buffer
const line = Array.from({ length: 38 }, (_, i) => i + 1).join(',')
function lifecycleStore(file, name, dependencies) {
  const defineStore = (_, options) => () => {
    const value = options.state()
    for (const [key, action] of Object.entries(options.actions)) value[key] = action.bind(value)
    return value
  }
  const source = readFileSync(new URL(file, import.meta.url), 'utf8')
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\r?$/gm, '').replace(/export /g, '')
  return new Function('defineStore', ...Object.keys(dependencies), source + `\nreturn ${name}();`)(defineStore, ...Object.values(dependencies))
}

describe('actual BLE collection wiring', () => {
  let store, native, patient, operator, requests, storage, deleteApi
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-19T00:00:00.000Z'))
    patient = { currentId: 7, savedRegistration }
    operator = { operator: { clinicianId: 11 }, unlocked: true, authRuntime: { authEpoch: 1 } }
    requests = []
    storage = new Map()
    deleteApi = async () => {}
    globalThis.uni = { showLoading: vi.fn(), hideLoading: vi.fn(), showToast: vi.fn(),
      getStorageSync: k => storage.get(k), setStorageSync: (k, v) => storage.set(k, v) }
    class Ble {
      connect(code, auto, callback) { this.connection = callback; callback({ type: 0 }) }
      scanServices(callback) { callback({ data: [null, null, { uuid: 'service', characteristics: [{ uuid: 'notify', properties: { NOTIFY: true } }] }] }) }
      setMtu() {}
      onNotityReadBleData(s, c, enabled, callback) { if (enabled) this.notification = callback }
      close() {}
    }
    const defineStore = (_, options) => () => {
      const value = options.state()
      for (const [k, action] of Object.entries(options.actions)) value[k] = action.bind(value)
      for (const [k, getter] of Object.entries(options.getters)) Object.defineProperty(value, k, { get: () => getter(value) })
      return value
    }
    const apiSource = readFileSync(new URL('../api/device.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
    const instance = { request: async config => {
      requests.push(config)
      const pieces = config.url.split('/')
      const captureId = config.url.endsWith('/collection-sessions') ? config.data.capture_id : pieces[pieces.length - 2]
      if (config.url.endsWith('/batches')) return { capture_id: captureId, results: config.data.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: '2026-10-19T00:00:03.000Z' })) }
      if (config.url.endsWith('/stop')) return collectionStopReceipt(captureId, config.data)
      return { capture_id: captureId }
    } }
    const api = new Function('instance', apiSource + '\nreturn { createCollectionApi, uploadCollectionBatchApi, stopCollectionApi };')(instance)
    let nextId = 0
    store = loadStore({ defineStore, store: {}, BleLib: Ble,
      listDevicesApi: async () => [], registerDeviceApi: async () => {}, deleteDeviceApiReq: (...args) => deleteApi(...args),
      usePatientStoreWithOut: () => patient, useOperatorStoreWithOut: () => operator,
      createBleLines, parseTelemetry, createCollectionCoordinator,
      useRadarStoreWithOut: () => ({ invalidateCapture() {}, suspendContext() {}, setForeground() {} }),
      createCollectionSession: options => createCollectionSession({ ...options, uuid: () => `00000000-0000-4000-8000-${String(++nextId).padStart(12, '0')}` }),
      ...api,
    })
    native = new Ble()
    store.deviceList = [{ id: 3, device_code: 'IN-3' }]
    store.bles_objs['IN-3'] = { ble: native, isConnected: false }
    store.isBluetoothOpen = true
  })

  function loadPatient(profile = { id: 7, subject_id: '#00007', ...savedRegistration(7).patient_snapshot, phone: null }, overrides = {}) {
    const getPatientProfileApi = vi.fn(async () => profile)
    const savePatientProfileApi = vi.fn(async (id, update) => ({ ...profile, ...update, id }))
    const listPatientsApi = async () => [{ id: profile.id, subject_id: profile.subject_id, name: profile.name,
      phone: profile.phone, age: profile.age, gender: profile.gender }]
    patient = lifecycleStore('../store/modules/patient.js', 'usePatientStore', {
      store: {}, getPatients: () => [], getCurrentPatientId: () => 7, setCurrentPatientId: () => {}, setPatients: () => {},
      normalizePatient, normalizePatientProfile, createRegistrationDraft, getPatientProfileApi, savePatientProfileApi, listPatientsApi,
      useBlueToothStoreWithOut: () => store, useOperatorStoreWithOut: () => operator,
      ...overrides,
    })
    return { getPatientProfileApi, savePatientProfileApi }
  }

  function loadHome(watch = () => {}, result = 'openStartConfirmation') {
    const source = readFileSync(new URL('../pages/home/home.vue', import.meta.url), 'utf8')
      .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
    uni.showModal = vi.fn()
    return new Function('useBlueToothStore', 'usePatientStoreWithOut', 'useOperatorStoreWithOut', 'ref', 'computed', 'reactive', 'watch', 'COLLECTION_TEST_TYPES',
      source + `\nreturn ${result};`)(
      () => store, () => patient, () => operator, value => ({ value }), get => ({ get value() { return get() } }), value => value, watch, COLLECTION_TEST_TYPES)
  }

  it('keeps selected profile measurements across the legacy list and updates the displayed patient after PUT', async () => {
    loadPatient()
    await patient.prepareRegistration()
    await patient.loadList()
    expect(patient.patients[0]).toMatchObject({ height_cm: 170, weight_kg: 65, shoe_size_eu: 40.5, phone: null })
    patient.editRegistration({ name: '更新姓名', test_type: 'tug' })
    await patient.saveRegistration()
    expect(patient.patients[0]).toMatchObject({ name: '更新姓名', height_cm: 170, phone: null })
  })

  it('refreshes the selected profile before PUT and exposes conflicts for an explicit choice', async () => {
    const profile = { id: 7, subject_id: '#00007', ...savedRegistration(7).patient_snapshot, phone: null }
    const { getPatientProfileApi, savePatientProfileApi } = loadPatient(profile)
    await patient.prepareRegistration()
    patient.editRegistration({ height_cm: '175', test_type: 'tug', remarks: '保留备注' })
    getPatientProfileApi.mockResolvedValue({ ...profile, height_cm: 180, weight_kg: 68 })
    await patient.saveRegistration()
    expect(savePatientProfileApi).not.toHaveBeenCalled()
    expect(patient.registrationState).toMatchObject({ ready: false, conflicts: [{ field: 'height_cm', serverValue: 180 }],
      form: { height_cm: '175', weight_kg: 68, remarks: '保留备注' } })
    patient.resolveRegistrationConflict({ field: 'height_cm', keepLocal: false })
    await patient.saveRegistration()
    expect(savePatientProfileApi).toHaveBeenCalledWith(7, expect.objectContaining({ height_cm: 180, weight_kg: 68 }), expect.anything())
    expect(patient.savedRegistration()).toMatchObject({ test_type: 'tug', remarks: '保留备注' })
  })

  it('drops a late create response before cache, patient selection or navigation changes under the new identity', async () => {
    let finish
    const profile = { ...savedRegistration(7).patient_snapshot, phone: null }
    const createPatientApi = vi.fn(() => new Promise(resolve => { finish = resolve }))
    const setPatients = vi.fn(), setCurrentPatientId = vi.fn()
    loadPatient(undefined, { createPatientApi, setPatients, setCurrentPatientId })
    const source = readFileSync(new URL('../pages/patient/new.vue', import.meta.url), 'utf8')
      .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
    const page = new Function('reactive', 'ref', 'usePatientStoreWithOut', 'useOperatorStoreWithOut', 'normalizePatientProfile',
      source + '\nreturn { f, onCreate };')(value => value, value => ({ value }), () => patient, () => operator, normalizePatientProfile)
    uni.switchTab = vi.fn()
    Object.assign(page.f, profile)
    const creating = page.onCreate()
    expect(createPatientApi).toHaveBeenCalledWith(profile, { collectionIdentity: { clinicianId: 11, authEpoch: 1 } })
    operator.operator.clinicianId = 12
    operator.authRuntime.authEpoch = 2
    patient.currentId = 9
    finish({ id: 7, subject_id: '#00007', ...profile })
    await creating
    expect(patient.currentId).toBe(9)
    expect(setPatients).not.toHaveBeenCalled()
    expect(setCurrentPatientId).not.toHaveBeenCalled()
    expect(uni.switchTab).not.toHaveBeenCalled()
    const creatingNow = page.onCreate()
    finish({ id: 10, subject_id: '#00010', ...profile })
    await creatingNow
    expect(setCurrentPatientId).toHaveBeenCalledWith(10)
    expect(uni.switchTab).toHaveBeenCalledOnce()
  })

  it('reopens start after cancellation and a quick retry during the old 300 ms close window', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    patient.registrationState = { ready: true }
    const openStartConfirmation = loadHome()
    openStartConfirmation()
    const first = uni.showModal.mock.calls[0][0]
    first.success({ cancel: true })
    openStartConfirmation()
    expect(uni.showModal).toHaveBeenCalledTimes(2)
    const second = uni.showModal.mock.calls[1][0]
    first.complete()
    openStartConfirmation()
    expect(uni.showModal).toHaveBeenCalledTimes(2)
    second.complete()
    await vi.advanceTimersByTimeAsync(300)
    expect(store.collectionState.active).toBeNull()
    expect(storage.has('collection_queue_v1')).toBe(false)
    openStartConfirmation()
    expect(uni.showModal).toHaveBeenCalledTimes(3)
    const third = uni.showModal.mock.calls[2][0]
    third.success({ confirm: true })
    third.success({ confirm: true })
    third.complete()
    expect(JSON.parse(storage.get('collection_queue_v1')).sessions).toHaveLength(1)
  })

  it('keeps the modified App registration and validation copy in Chinese', () => {
    for (const file of ['../components/CollectionRegistration.vue', '../pages/home/home.vue', '../pages/patient/new.vue',
      '../utils/patient.js', '../utils/collectionRegistration.js', '../store/modules/patient.js', '../store/modules/blueTooth.js']) {
      const source = readFileSync(new URL(file, import.meta.url), 'utf8')
      expect(source, file).not.toMatch(/\s\/\s(?:[A-Z][a-z]+)\b/)
    }
  })
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); delete globalThis.uni })

  it('reassembles a split 38-value notification before refreshing realtime', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    native.notification({ data: bytes(line.slice(0, 23)) })
    native.notification({ data: bytes(line.slice(23) + '\r\n') })
    expect(store.realtime.hasData).toBe(true)
    expect(store.realtime.left.speed).toBe(17)
    expect(requests).toEqual([])
  })
  it('sends the actual device API create → split-stream batches → stop with fixed patient and independent speeds', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    native.notification({ data: bytes(line + '\n') })
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes('GPS1,1,0,,,,2.7,0,,0,,0,0\n' + line + '\n') })
    store.stopCollection()
    await store.retryCollectionUpload()
    const id = requests[0].data.capture_id
    expect(requests.map(r => r.url)).toEqual(['/v2/collection-sessions', `/collection-sessions/${id}/batches`,
      `/collection-sessions/${id}/batches`, `/v2/collection-sessions/${id}/stop`])
    expect(requests[0].data.patient_id).toBe(7)
    expect(requests[0].custom.collectionIdentity).toMatchObject({ clinicianId: 11, authEpoch: 1 })
    expect(requests[1].data.events[0]).toMatchObject({ stream: 'gps', stream_sequence: 0, connection_epoch: 1 })
    expect(requests[2].data.events[0].payload).toMatchObject({ left_speed: 17, right_speed: 36 })
    const counts = { insole: 1, gps: 1, radar: 0 }
    expect(store.collectionUpload).toMatchObject({ capture_id: id, upload_state: 'verified', received_counts: counts })
    patient.currentId = 8
    expect(store.collectionUpload).toBeNull()
    patient.currentId = 7
    operator.operator.clinicianId = 12
    expect(store.collectionUpload).toBeNull()
    operator.operator.clinicianId = 11
    operator.unlocked = false
    expect(store.collectionUpload).toBeNull()
    expect(store.gpsRealtime.speed).toBe(2.7)
    expect(store.realtime.left.speed).toBe(17)
  })
  it('shows a durable completion after cold start unlock without making another upload request', () => {
    const counts = { insole: 1, gps: 0, radar: 0 }
    const stamp = '2026-10-19T00:00:00.000Z'
    const { verification } = collectionStopReceipt('finished', { schema_version: 2, mobile_stopped_at: stamp, final_counts: counts })
    storage.set('collection_queue_v1', JSON.stringify({ version: 3, last_capture_sequence: 1, sessions: [], completed: [{ capture_id: 'finished',
      clinicianId: 11, patient_id: 7, mobile_started_at: stamp, mobile_stopped_at: stamp, test_type: 'tug', capture_sequence: 1, verification }] }))
    operator.unlocked = false
    store.ensureCollection()
    expect(store.collectionUpload).toBeNull()
    operator.unlocked = true
    patient.prepareRegistration = vi.fn()
    const homeReceipt = loadHome((_, callback, options) => { if (options.immediate) callback() }, 'uploadRecordDetails.value')
    expect(store.collectionUpload).toMatchObject({ capture_id: 'finished', upload_state: 'verified', received_counts: counts })
    expect(homeReceipt).toEqual({ captureId: 'finished', typeLabel: 'TUG综合测试', startedAt: '2026-10-19 00:00:00.000 UTC',
      stoppedAt: '2026-10-19 00:00:00.000 UTC' })
    expect(requests).toEqual([])
  })
  it('shows the stopped capture type and times from its frozen registration on the actual home page', async () => {
    store.bles_objs['IN-3'].isConnected = true
    let registration = { ...savedRegistration(7), test_type: 'tug' }
    patient.savedRegistration = () => registration
    store.startCollection('IN-3', registration)
    const firstId = store.collectionState.active.capture_id
    vi.setSystemTime(new Date('2026-10-19T00:00:03.000Z'))
    store.stopCollection()
    registration = { ...registration, test_type: 'static_standing' }
    const firstDetails = { captureId: firstId, typeLabel: 'TUG综合测试',
      startedAt: '2026-10-19 00:00:00.000 UTC', stoppedAt: '2026-10-19 00:00:03.000 UTC' }
    expect(store.collectionUpload).toMatchObject({ capture_id: firstId, test_type: 'tug', upload_state: 'pending' })
    expect(loadHome(undefined, 'uploadRecordDetails.value')).toEqual(firstDetails)
    await store.retryCollectionUpload()
    expect(store.collectionUpload.upload_state).toBe('verified')
    expect(loadHome(undefined, 'uploadRecordDetails.value')).toEqual(firstDetails)
    store.startCollection('IN-3', registration)
    expect(loadHome(undefined, 'uploadRecordDetails.value')).toMatchObject({ typeLabel: '静止站立测试', stoppedAt: '—' })
  })
  it('uploads the exact GPS sample with time-only UTC unchanged alongside insole data', async () => {
    const raw = 'GPS1,42,1,31.2304000,121.4737000,12.5,1.20,8,0.95,180,083015.00,14632,0'
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: Array.from(new Uint8Array(bytes(line + '\r\n' + raw + '\r\n'))) })
    expect(store.gpsRealtime).toMatchObject({ seq: 42, lat: 31.2304, lon: 121.4737, utc: '083015.00', speed: 1.2 })
    expect(store.collectionState.rejected).toBe(0)
    store.stopCollection()
    await store.retryCollectionUpload()
    const events = requests.filter(r => r.url.endsWith('/batches')).flatMap(r => r.data.events)
    expect(events.find(e => e.stream === 'gps').payload).toEqual({ raw_line: raw })
    expect(events.find(e => e.stream === 'insole').payload).toMatchObject({ left_speed: 17, right_speed: 36 })
    expect(store.collectionState.queue.pending).toBe(0)
  })
  it('distinguishes GPS rejections from other rows and keeps accepting subsequent valid telemetry', async () => {
    const raw = 'GPS1,42,1,31.2304000,121.4737000,12.5,1.20,8,0.95,180,083015.00,14632,0'
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    native.notification({ data: bytes(raw.replace(',8,', ',8x,') + '\n') })
    expect(store.collectionState).toMatchObject({ gpsRejected: 1, gpsReceived: 0, insoleReceived: 0,
      gpsLastError: '第 8 字段格式错误' })
    native.notification({ data: bytes('unrecognized status\n' + line + '\n' + raw + '\n') })
    expect(store.collectionState).toMatchObject({ rejected: 2, gpsRejected: 1, gpsReceived: 1, insoleReceived: 1 })
    expect(store.gpsRealtime.utc).toBe('083015.00')
    expect(store.realtime.hasData).toBe(true)
    expect(JSON.stringify(store.collectionState)).not.toContain('31.2304')
    expect(requests).toEqual([])
  })
  it('reports GPS field-count and runtime errors without changing the recording or swallowing later rows', async () => {
    const raw = 'GPS1,42,1,31.2304000,121.4737000,12.5,1.20,8,0.95,180,083015.00,14632,0'
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes('GPS1,42,1\n') })
    expect(store.collectionState.gpsLastError).toBe('字段数量为 3，应为 13')
    const descriptor = Object.getOwnPropertyDescriptor(Number, 'isSafeInteger')
    try {
      Object.defineProperty(Number, 'isSafeInteger', { value: undefined, configurable: true })
      native.notification({ data: bytes(raw + '\n' + line + '\n') })
    } finally { Object.defineProperty(Number, 'isSafeInteger', descriptor) }
    expect(store.collectionState.gpsLastError).toBe('解析执行异常（请反馈手机系统与 App 版本）')
    expect(store.collectionState).toMatchObject({ gpsRejected: 2, insoleReceived: 1, rejected: 2 })
    expect(store.collectionState.active).not.toBeNull()
    native.notification({ data: bytes(raw + '\n') })
    store.stopCollection()
    await store.retryCollectionUpload()
    expect(store.collectionState.queue.pending).toBe(0)
    const events = requests.filter(r => r.url.endsWith('/batches')).flatMap(r => r.data.events)
    expect(events.map(e => e.stream)).toEqual(['insole', 'gps'])
    expect(events[1].payload.raw_line).toBe(raw)
  })
  it('records no-fix nan GPS messages, previews missing values and uploads raw lines unchanged', async () => {
    const rows = ['GPS1,5,0,nan,nan,nan,nan,0,99.99,617,,16607,0',
      'GPS1,6,0,nan,nan,nan,nan,0,99.99,626,,17551,0']
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    const text = rows[0] + '\r\n' + line + '\n' + rows[1] + '\n'
    native.notification({ data: Array.from(new Uint8Array(bytes(text.slice(0, 20)))) })
    native.notification({ data: Array.from(new Uint8Array(bytes(text.slice(20)))) })
    expect(store.collectionState).toMatchObject({ gpsReceived: 2, gpsRejected: 0, rejected: 0, insoleReceived: 1 })
    expect(store.gpsRealtime).toMatchObject({ seq: 6, fix: false, lat: null, lon: null, alt: null,
      speed: null, hdop: 99.99, utc: '', chars: 17551 })
    store.stopCollection()
    await store.retryCollectionUpload()
    const events = requests.filter(r => r.url.endsWith('/batches')).flatMap(r => r.data.events)
    expect(events.filter(e => e.stream === 'gps').map(e => e.payload.raw_line)).toEqual(rows)
    expect(events.filter(e => e.stream === 'insole')).toHaveLength(1)
    expect(store.collectionState.queue.pending).toBe(0)
  })
  it('shows pressure and IMU and uploads 38 fields from numeric-array BLE notifications', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: Array.from(new Uint8Array(bytes(line + '\n'))) })
    expect(store.realtime.hasData).toBe(true)
    expect(store.realtime.left.pressure).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9])
    expect(store.realtime.left.imu).toMatchObject({ ax: 10, ay: 11, az: 12 })
    expect(store.realtime.right.imu).toMatchObject({ ax: 29, ay: 30, az: 31 })
    store.stopCollection()
    await store.retryCollectionUpload()
    const batches = requests.filter(r => r.url.endsWith('/batches'))
    expect(batches).toHaveLength(1)
    expect(batches[0].data.events[0].stream).toBe('insole')
    expect(Object.keys(batches[0].data.events[0].payload)).toHaveLength(38)
    expect(batches[0].data.events[0].payload).toMatchObject({ lp1: 1, ax: 10, rp1: 20, right_ax: 29 })
  })
  it('stops before changed patient can receive a new sample', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes(line + '\n') })
    patient.currentId = 8
    native.notification({ data: bytes(line + '\n') })
    await store.retryCollectionUpload()
    expect(store.collectionState.active).toBe(null)
    expect(requests.filter(r => r.url.endsWith('/batches'))).toHaveLength(1)
    expect(requests[0].data.patient_id).toBe(7)
  })
  it('preserves capture on unexpected disconnect, resets partial rows and ignores old callbacks', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    const capture = store.collectionState.active.capture_id
    const oldNotify = native.notification
    oldNotify({ data: bytes('GPS1,1,') })
    native.connection({ type: 10006 })
    expect(store.collectionState.waiting).toBe(true)
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    oldNotify({ data: bytes(line + '\n') })
    native.notification({ data: bytes(line + '\n') })
    store.disconnectDevice(3)
    await store.retryCollectionUpload()
    expect(requests[0].data.capture_id).toBe(capture)
    const batches = requests.filter(r => r.url.endsWith('/batches'))
    expect(batches).toHaveLength(1)
    expect(batches[0].data.events).toHaveLength(1)
    expect(batches[0].data.events[0].connection_epoch).toBe(3)
    expect(store.collectionState.active).toBe(null)
  })
  it('does not subscribe after active disconnect during the subscription delay', async () => {
    store.connectDevice(3)
    store.disconnectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    expect(native.notification).toBe(undefined)
  })
  it('ignores a late successful callback from the failed first connection attempt', async () => {
    const callbacks = []
    native.connect = (code, auto, callback) => {
      callbacks.push(callback)
      callback({ type: callbacks.length === 1 ? 10003 : 0 })
    }
    const scans = vi.spyOn(native, 'scanServices')
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(600)
    callbacks[0]({ type: 0 })
    expect(scans).toHaveBeenCalledTimes(1)
  })
  it('retires a failed attempt immediately throughout the 600ms retry backoff', async () => {
    const callbacks = []
    native.connect = (code, auto, callback) => {
      callbacks.push(callback)
      if (callbacks.length === 1) callback({ type: 10003 })
      else callback({ type: 0 })
    }
    const scans = vi.spyOn(native, 'scanServices')
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(300)
    callbacks[0]({ type: 0 })
    expect(store.bles_objs['IN-3'].isConnected).toBe(false)
    expect(scans).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(300)
    expect(callbacks).toHaveLength(2)
    expect(scans).toHaveBeenCalledTimes(1)
  })
  it('rejects a late success after the final retry has already failed', async () => {
    const callbacks = []
    native.connect = (code, auto, callback) => { callbacks.push(callback); callback({ type: 10003 }) }
    const scans = vi.spyOn(native, 'scanServices')
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(600)
    expect(callbacks).toHaveLength(2)
    callbacks[1]({ type: 0 })
    expect(store.bles_objs['IN-3'].isConnected).toBe(false)
    expect(store.bles_objs['IN-3'].connecting).toBe(false)
    expect(scans).not.toHaveBeenCalled()
  })
  it('still performs timeout and native close while a failed attempt is retired', async () => {
    const callbacks = []
    native.connect = (code, auto, callback) => { callbacks.push(callback) }
    native.close = vi.fn()
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(9900)
    callbacks[0]({ type: 10003 })
    await vi.advanceTimersByTimeAsync(100)
    expect(native.close).toHaveBeenCalledOnce()
    expect(store.bles_objs['IN-3'].connecting).toBe(false)
    await vi.advanceTimersByTimeAsync(600)
    expect(callbacks).toHaveLength(1)
  })
  it('always closes the native connection even if disabling notification throws', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    native.close = vi.fn()
    native.onNotityReadBleData = () => { throw Error('already released') }
    store.disconnectDevice(3)
    expect(native.close).toHaveBeenCalledOnce()
  })
  it('ends recording before the delete request even when deletion fails', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes(line + '\n') })
    let activeAtDelete = 'not-called'
    deleteApi = async () => { activeAtDelete = store.collectionState.active; throw Error('network') }
    await store.deleteDevice(3)
    expect(activeAtDelete).toBe(null)
    expect(store.bles_objs['IN-3'].isConnected).toBe(false)
    expect(store.collectionState.queue.pending).toBe(1)
  })
  it('hides and preserves a pending capture until its original clinician returns', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    const captureId = store.collectionState.active.capture_id
    native.notification({ data: bytes(line + '\n') })
    store.endCollectionContext()
    expect(store.collectionState.queue.pending).toBe(1)
    const savedQueue = storage.get('collection_queue_v1')
    const [savedCapture] = JSON.parse(savedQueue).sessions
    expect(savedCapture).toMatchObject({ capture_id: captureId, clinicianId: 11, patient_id: 7 })
    expect(savedCapture.outboxes.primary).toHaveLength(1)

    operator.operator.clinicianId = 12
    operator.authRuntime.authEpoch = 2
    await store.retryCollectionUpload()
    expect(requests).toEqual([])
    expect(store.collectionState.queue).toMatchObject({ pending: 0, sessions: 0, uploads: [] })
    expect(store.collectionUpload).toBeNull()
    expect(storage.get('collection_queue_v1')).toBe(savedQueue)

    operator.operator.clinicianId = 11
    operator.authRuntime.authEpoch = 3
    store.refreshCollectionStatus()
    expect(store.collectionState.queue.pending).toBe(1)
    expect(store.collectionUpload).toMatchObject({ capture_id: captureId, clinicianId: 11, patient_id: 7, upload_state: 'pending' })
    await store.retryCollectionUpload()
    expect(requests.map(request => request.url)).toEqual([
      '/v2/collection-sessions', `/collection-sessions/${captureId}/batches`, `/v2/collection-sessions/${captureId}/stop`,
    ])
    expect(requests[0].data).toMatchObject({ capture_id: captureId, patient_id: 7 })
    expect(requests[1].data.events).toEqual(savedCapture.outboxes.primary)
    for (const request of requests) {
      expect(request.custom.collectionIdentity).toMatchObject({ clinicianId: 11, authEpoch: 3 })
    }
    expect(store.collectionState.queue.pending).toBe(0)
    expect(store.collectionUpload).toMatchObject({ capture_id: captureId, upload_state: 'verified' })
  })
  it('actual patient select action closes the old window before assigning another patient', async () => {
    const { getPatientProfileApi, savePatientProfileApi } = loadPatient()
    const openStartConfirmation = loadHome()
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    openStartConfirmation()
    expect(uni.showModal).not.toHaveBeenCalled()
    await patient.prepareRegistration()
    expect(patient.registrationState.form).toMatchObject({ height_cm: 170, phone: null })
    expect(getPatientProfileApi).toHaveBeenCalledWith(7, { collectionIdentity: { clinicianId: 11, authEpoch: 1 } })
    patient.editRegistration({ test_type: 'tug', remarks: '登记备注' })
    await patient.saveRegistration()
    expect(savePatientProfileApi).toHaveBeenCalledWith(7, expect.objectContaining({ height_cm: 170, phone: null }),
      { collectionIdentity: { clinicianId: 11, authEpoch: 1 } })
    expect(store.collectionState.active).toBe(null)
    expect(storage.has('collection_queue_v1')).toBe(false)
    openStartConfirmation()
    const cancelled = uni.showModal.mock.calls[0][0]
    cancelled.success({ cancel: true })
    cancelled.success({ confirm: true })
    expect(storage.has('collection_queue_v1')).toBe(false)
    openStartConfirmation()
    const confirmed = uni.showModal.mock.calls[1][0]
    confirmed.success({ confirm: true })
    confirmed.success({ confirm: true })
    expect(store.collectionState.active.registration).toMatchObject({ patient_id: 7, test_type: 'tug', remarks: '登记备注' })
    expect(JSON.parse(storage.get('collection_queue_v1')).sessions).toHaveLength(1)
    patient.editRegistration({ remarks: '采集中尝试编辑' })
    await patient.saveRegistration()
    expect(patient.registrationState.form.remarks).toBe('登记备注')
    expect(savePatientProfileApi).toHaveBeenCalledTimes(1)
    native.notification({ data: bytes(line + '\n') })
    patient.select(8)
    expect(store.collectionState.active).toBe(null)
    expect(store.collectionState.reason).toBe('patient')
    native.notification({ data: bytes(line + '\n') })
    await store.retryCollectionUpload()
    expect(requests[0].data.patient_id).toBe(7)
    expect(requests.filter(r => r.url.endsWith('/batches'))[0].data.events).toHaveLength(1)
  })
  it('actual operator reset closes BLE and retains pending under its original clinician', async () => {
    operator = lifecycleStore('../store/modules/operator.js', 'useOperatorStore', {
      store: {}, getOperator: () => ({ clinicianId: 11 }), createOperatorSessionRuntime, resetOperatorSession,
      clearOperator: () => {}, clearToken: () => {}, useBlueToothStoreWithOut: () => store,
    })
    operator.unlocked = true
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes(line + '\n') })
    operator.reset()
    await store.retryCollectionUpload()
    expect(store.collectionState.active).toBe(null)
    expect(store.bles_objs['IN-3'].isConnected).toBe(false)
    expect(operator.unlocked).toBe(false)
    expect(requests).toEqual([])
    expect(JSON.parse(storage.get('collection_queue_v1')).sessions[0].clinicianId).toBe(11)
  })
  it('actual App onHide stops capture, releases wake lock, and keeps pending data', async () => {
    uni.setKeepScreenOn = vi.fn()
    const source = readFileSync(new URL('../App.vue', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1]
      .replace(/^import .*$/gm, '').replace('export default', 'return')
    const app = new Function('useBlueToothStoreWithOut', 'useRadarStoreWithOut', source)(() => store, () => ({ setForeground() {} }))
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3', savedRegistration(patient.currentId))
    native.notification({ data: bytes(line + '\n') })
    expect(uni.setKeepScreenOn).toHaveBeenLastCalledWith({ keepScreenOn: true })
    app.onHide()
    expect(store.collectionState.active).toBe(null)
    expect(store.collectionState.reason).toBe('background')
    expect(uni.setKeepScreenOn).toHaveBeenLastCalledWith({ keepScreenOn: false })
    expect(store.collectionState.queue.pending).toBe(1)
  })
})
