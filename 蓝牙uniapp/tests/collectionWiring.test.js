import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { createBleLines, parseTelemetry } from '../utils/bleTelemetry'
import { createCollectionSession } from '../utils/collectionSession'
import { createTelemetryQueue } from '../utils/telemetryQueue'
import { createOperatorSessionRuntime, resetOperatorSession } from '../utils/operatorSession'

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
    patient = { currentId: 7 }
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
      return value
    }
    const apiSource = readFileSync(new URL('../api/device.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
    const instance = { request: async config => {
      requests.push(config)
      const captureId = config.url === '/collection-sessions' ? config.data.capture_id : config.url.split('/')[2]
      if (config.url.endsWith('/batches')) return { capture_id: captureId, results: config.data.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: '2026-10-19T00:00:03.000Z' })) }
      return { capture_id: captureId }
    } }
    const api = new Function('instance', apiSource + '\nreturn { createCollectionApi, uploadCollectionBatchApi, stopCollectionApi };')(instance)
    let nextId = 0
    store = loadStore({ defineStore, store: {}, BleLib: Ble,
      listDevicesApi: async () => [], registerDeviceApi: async () => {}, deleteDeviceApiReq: (...args) => deleteApi(...args),
      usePatientStoreWithOut: () => patient, useOperatorStoreWithOut: () => operator,
      createBleLines, parseTelemetry, createTelemetryQueue,
      createCollectionSession: options => createCollectionSession({ ...options, uuid: () => `00000000-0000-4000-8000-${String(++nextId).padStart(12, '0')}` }),
      ...api,
    })
    native = new Ble()
    store.deviceList = [{ id: 3, device_code: 'IN-3' }]
    store.bles_objs['IN-3'] = { ble: native, isConnected: false }
    store.isBluetoothOpen = true
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
    store.startCollection('IN-3')
    native.notification({ data: bytes('GPS1,1,0,,,,2.7,0,,0,,0,0\n' + line + '\n') })
    store.stopCollection()
    await store.retryCollectionUpload()
    expect(requests.map(r => r.url.split('/').at(-1))).toEqual(['collection-sessions', 'batches', 'batches', 'stop'])
    expect(requests[0].data.patient_id).toBe(7)
    expect(requests[0].custom.collectionIdentity).toMatchObject({ clinicianId: 11, authEpoch: 1 })
    expect(requests[1].data.events[0]).toMatchObject({ stream: 'gps', stream_sequence: 0, connection_epoch: 1 })
    expect(requests[2].data.events[0].payload).toMatchObject({ left_speed: 17, right_speed: 36 })
    expect(store.gpsRealtime.speed).toBe(2.7)
    expect(store.realtime.left.speed).toBe(17)
  })
  it('stops before changed patient can receive a new sample', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3')
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
    store.startCollection('IN-3')
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
    store.startCollection('IN-3')
    native.notification({ data: bytes(line + '\n') })
    let activeAtDelete = 'not-called'
    deleteApi = async () => { activeAtDelete = store.collectionState.active; throw Error('network') }
    await store.deleteDevice(3)
    expect(activeAtDelete).toBe(null)
    expect(store.bles_objs['IN-3'].isConnected).toBe(false)
    expect(store.collectionState.queue.pending).toBe(1)
  })
  it('refuses to send a pending capture with a new clinician credential', async () => {
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3')
    native.notification({ data: bytes(line + '\n') })
    store.endCollectionContext()
    operator.operator.clinicianId = 12
    operator.authRuntime.authEpoch = 2
    await store.retryCollectionUpload()
    expect(requests).toEqual([])
    expect(store.collectionState.queue.pending).toBe(1)
  })
  it('actual patient select action closes the old window before assigning another patient', async () => {
    patient = lifecycleStore('../store/modules/patient.js', 'usePatientStore', {
      store: {}, getPatients: () => [], getCurrentPatientId: () => 7, setCurrentPatientId: () => {},
      useBlueToothStoreWithOut: () => store,
    })
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3')
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
    store.startCollection('IN-3')
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
    const app = new Function('useBlueToothStoreWithOut', source)(() => store)
    store.connectDevice(3)
    await vi.advanceTimersByTimeAsync(2000)
    store.startCollection('IN-3')
    native.notification({ data: bytes(line + '\n') })
    expect(uni.setKeepScreenOn).toHaveBeenLastCalledWith({ keepScreenOn: true })
    app.onHide()
    expect(store.collectionState.active).toBe(null)
    expect(store.collectionState.reason).toBe('background')
    expect(uni.setKeepScreenOn).toHaveBeenLastCalledWith({ keepScreenOn: false })
    expect(store.collectionState.queue.pending).toBe(1)
  })
})
