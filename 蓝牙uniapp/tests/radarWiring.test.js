import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { createRadarLink } from '../utils/radarLink'
import { createRadarDiscovery } from '../utils/radarDiscovery'
import { createCollectionCoordinator } from '../utils/collectionCoordinator'
import { createCollectionSession } from '../utils/collectionSession'
import { createBleLines, parseTelemetry } from '../utils/bleTelemetry'
const payload = { frames: 1, bytes: 30, age_ms: 1, stale: false, targets: [{ slot: 1, present: true, x_mm: 0, y_mm: 100, speed_cms: 5, resolution_mm: 10 }] }
function load(path, name, dependencies) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
  return new Function(...Object.keys(dependencies), source + `\nreturn ${name}();`)(...Object.values(dependencies))
}
let ble, radar, disk, sent, operator, patient, adapter, native, serial
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-23T00:00:00.000Z'))
  disk = new Map(); sent = []; serial = 0; patient = { currentId: 7 }; operator = { operator: { clinicianId: 11 }, unlocked: true, authRuntime: { authEpoch: 1 } }
  globalThis.uni = { getStorageSync: key => disk.get(key), setStorageSync: (key, value) => disk.set(key, value), setKeepScreenOn: vi.fn(), showToast: vi.fn(), showLoading: vi.fn(), hideLoading: vi.fn() }
  const defineStore = (_, options) => () => { const value = options.state(); for (const [key, action] of Object.entries(options.actions)) value[key] = action.bind(value); return value }
  class Ble { connect(code, auto, cb) { cb({ type: 0 }) } scanServices(cb) { cb({ data: [null, null, { uuid: 's', characteristics: [{ uuid: 'n', properties: { NOTIFY: true } }] }] }) } setMtu() {} onNotityReadBleData(s, n, enabled, cb) { if (enabled) this.notify = cb } close() {} }
  adapter = { capabilities: async () => ({ supported: true, permitted: true }), wifiScope: async () => ({ networkToken: 'wifi', address: '10.0.0.4', prefixLength: 30 }), resolveRadarName: async () => ['10.0.0.2'], readRadar: async () => payload, cancel: vi.fn() }
  const deps = { defineStore, store: {}, BleLib: Ble, usePatientStoreWithOut: () => patient, useOperatorStoreWithOut: () => operator,
    useBlueToothStoreWithOut: () => ble, useRadarStoreWithOut: () => radar, createBleLines, parseTelemetry, createCollectionCoordinator,
    createCollectionSession: opts => createCollectionSession({ ...opts, uuid: () => `00000000-0000-4000-8000-${String(++serial).padStart(12, '0')}` }),
    createCollectionApi: async body => { sent.push(['create', body]); return { capture_id: body.capture_id } },
    uploadCollectionBatchApi: async (id, body) => { sent.push(['batch', id, body]); return { capture_id: id, results: body.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: '2026-10-23T00:00:01.000Z' })) } },
    stopCollectionApi: async (id, body) => { sent.push(['stop', id, body]); return { capture_id: id } },
    createRadarNative: () => adapter, createRadarDiscovery, createRadarLink,
  }
  ble = load('../store/modules/blueTooth.js', 'useBlueToothStore', deps)
  radar = load('../store/modules/radar.js', 'useRadarStore', deps)
  native = new Ble(); ble.deviceList = [{ id: 3, device_code: 'IN-3' }]; ble.bles_objs['IN-3'] = { ble: native, isConnected: false }; ble.isBluetoothOpen = true
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); delete globalThis.uni })
it('actual BLE notification and HTTP frame enter the same capture and stop after all three streams', async () => {
  ble.connectDevice(3); await vi.advanceTimersByTimeAsync(2000)
  await radar.open(); await vi.advanceTimersByTimeAsync(0)
  expect(ble.ensureCollection().queue.snapshot().pending).toBe(0)
  ble.startCollection('IN-3')
  const text = Array.from({ length: 38 }, (_, i) => i + 1).join(',') + '\nGPS1,1,0,,,,2.7,0,,0,,0,0\n'
  native.notify({ data: Uint8Array.from([...text].map(c => c.charCodeAt(0))).buffer })
  await vi.advanceTimersByTimeAsync(200); ble.stopCollection(); await ble.retryCollectionUpload()
  const streams = sent.filter(r => r[0] === 'batch').flatMap(r => r[2].events.map(e => e.stream))
  expect(new Set(streams)).toEqual(new Set(['insole', 'gps', 'radar']))
  expect(sent.filter(r => r[0] === 'create')).toHaveLength(1); expect(sent.filter(r => r[0] === 'stop')).toHaveLength(1)
})
it('an HTTP response begun before capture start cannot enter a new capture', async () => {
  ble.bles_objs['IN-3'].isConnected = true
  let finish
  adapter.readRadar = () => new Promise(resolve => { finish = resolve })
  await radar.connect('10.0.0.2'); await vi.advanceTimersByTimeAsync(0)
  ble.startCollection('IN-3'); finish(payload); await vi.advanceTimersByTimeAsync(0)
  expect(ble.collectionState.queue.radarPending).toBe(0)
})
it('actual App background stops all recording and foreground never reopens capture', async () => {
  ble.bles_objs['IN-3'].isConnected = true; await radar.open(); await vi.advanceTimersByTimeAsync(0); ble.startCollection('IN-3')
  const source = readFileSync(new URL('../App.vue', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'return')
  const app = new Function('useBlueToothStoreWithOut', 'useRadarStoreWithOut', source)(() => ble, () => radar)
  app.onHide(); await vi.advanceTimersByTimeAsync(1000)
  expect(ble.collectionState.active).toBe(null); expect(radar.connection.status).toBe('background')
  app.onShow(); await vi.advanceTimersByTimeAsync(1000)
  expect(ble.collectionState.active).toBe(null)
})
it('permission denial leaves the old BLE/GPS capture usable', async () => {
  adapter.capabilities = async () => ({ supported: true, permitted: false }); await radar.open()
  ble.bles_objs['IN-3'].isConnected = true; ble.startCollection('IN-3')
  expect(ble.collectionState.active.patient_id).toBe(7); expect(radar.connection.status).toBe('permission')
})
it('a stopped capture cannot leak a late native response into the next patient window', async () => {
  ble.bles_objs['IN-3'].isConnected = true
  let finishOld
  adapter.readRadar = () => new Promise(resolve => { finishOld = resolve })
  ble.startCollection('IN-3'); await radar.connect('10.0.0.2'); await vi.advanceTimersByTimeAsync(0)
  const oldCapture = ble.collectionState.active.capture_id
  const old = finishOld
  ble.stopCollection('patient'); patient.currentId = 8; ble.startCollection('IN-3')
  old(payload); await vi.advanceTimersByTimeAsync(0)
  expect(ble.collectionState.active.patient_id).toBe(8)
  expect(ble.collectionState.queue.radarPending).toBe(0)
  await vi.advanceTimersByTimeAsync(200); finishOld(payload); await vi.advanceTimersByTimeAsync(0)
  expect(ble.collectionState.queue.radarPending).toBe(1)
  const durable = JSON.parse(disk.get('collection_queue_v1')).sessions
  expect(durable.filter(s => s.outboxes.radar.length).map(s => [s.patient_id, s.outboxes.radar.length])).toEqual([[8, 1]])
  expect(sent.filter(r => r[0] === 'stop').map(r => r[1])).toContain(oldCapture)
})
it('logout cancels native polling and a later App foreground cannot restart it', async () => {
  await radar.open(); await vi.advanceTimersByTimeAsync(0)
  const read = vi.spyOn(adapter, 'readRadar')
  ble.endCollectionContext('identity'); operator.unlocked = false
  radar.setForeground(false); radar.setForeground(true); await vi.advanceTimersByTimeAsync(60000)
  expect(read).not.toHaveBeenCalled(); expect(radar.realtime).toBe(null)
})
