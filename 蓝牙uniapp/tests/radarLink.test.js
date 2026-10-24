import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { createRadarLink } from '../utils/radarLink'
const payload = (frames = 1) => ({ frames, bytes: 30, age_ms: 1, stale: false, targets: [] })
const candidates = ips => ({ networkToken: 'wifi', candidates: ips.map(ip => ({ ip, frames: 1, stale: false })) })
function fixture(discover = async () => candidates(['10.0.0.2'])) {
  const states = [], frames = [], reads = []
  const adapter = { capabilities: async () => ({ supported: true, permitted: true }), wifiScope: async () => ({ networkToken: 'wifi', address: '10.0.0.4', prefixLength: 24 }), cancel: vi.fn(), readRadar: async (ip, timeout, id, expectedScope, subnetOnly) => { reads.push([ip, timeout, id, expectedScope, subnetOnly]); return payload() } }
  const discovery = { discover, cancel: vi.fn() }
  return { adapter, discovery, states, frames, reads, link: createRadarLink({ adapter, discovery, onState: s => states.push(s), onFrame: (...f) => frames.push(f) }) }
}
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())
it('test_multiple_candidates_require_selection', async () => {
  const f = fixture(async () => candidates(['10.0.0.2', '10.0.0.3']))
  await f.link.enable(); await vi.advanceTimersByTimeAsync(1000)
  expect(f.reads).toEqual([])
  expect(f.states.at(-1).status).toBe('selection')
  await f.link.connect('10.0.0.3'); await vi.advanceTimersByTimeAsync(0)
  expect(f.reads[0].slice(0, 2)).toEqual(['10.0.0.3', 2500])
})
it('test_cancel_blocks_late_connect', async () => {
  let resolve
  const f = fixture(() => new Promise(r => { resolve = r }))
  const enabling = f.link.enable(); f.link.disconnect(); resolve(candidates(['10.0.0.2'])); await enabling
  await vi.advanceTimersByTimeAsync(30000)
  expect(f.reads).toEqual([])
})
it('keeps telemetry single flight and advances epoch on counter rollback', async () => {
  const f = fixture(); let n = 0
  f.adapter.readRadar = async () => payload(++n === 1 ? 7 : 1)
  await f.link.enable(); await vi.advanceTimersByTimeAsync(200)
  expect(f.frames).toHaveLength(2)
  expect(f.frames[1][2]).toBeGreaterThan(f.frames[0][2])
  f.link.setForeground(false); await vi.advanceTimersByTimeAsync(5000)
  expect(f.frames).toHaveLength(2)
})
it('rediscovers after three network failures with at least 30 seconds between rounds', async () => {
  const f = fixture(); const discover = vi.spyOn(f.discovery, 'discover')
  f.adapter.readRadar = async () => { throw Error('network') }
  await f.link.enable(); await vi.advanceTimersByTimeAsync(1200)
  expect(discover).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(28800)
  expect(discover).toHaveBeenCalledTimes(2)
  f.link.disconnect(); await vi.advanceTimersByTimeAsync(60000)
  expect(discover).toHaveBeenCalledTimes(2)
})
it('a protocol error breaks the run of consecutive network failures', async () => {
  const f = fixture(); let count = 0
  f.adapter.readRadar = async () => { count++; if (count === 2) return '{}'; throw Error('network') }
  await f.link.enable(); await vi.advanceTimersByTimeAsync(1200)
  expect(f.states.at(-1).status).toBe('network')
  expect(f.states.at(-1).failures).toBe(2)
  expect(f.states.filter(s => s.status === 'network').map(s => s.failures)).toEqual([1, 1, 2])
  f.link.dispose()
})

it('test_manual_private_ip_poll_forwards_expected_scope_without_subnet_scan', async () => {
  const f = fixture(), reads = []
  f.adapter.wifiScope = async () => ({ networkToken: 'wifi', address: '10.0.0.4', prefixLength: 24 })
  f.adapter.readRadar = async (...args) => { reads.push(args); return payload() }
  await f.link.connect('192.168.8.9'); await vi.advanceTimersByTimeAsync(0)
  expect(reads[0].slice(3)).toEqual([{ networkToken: 'wifi', address: '10.0.0.4', prefixLength: 24 }, false])
  expect(f.frames).toHaveLength(1)
  f.link.dispose()
})
it('capture cancellation cannot start another telemetry request inside the 5Hz budget', async () => {
  const f = fixture(), starts = []
  f.adapter.readRadar = () => { starts.push(Date.now()); return new Promise(() => {}) }
  await f.link.enable(); await vi.advanceTimersByTimeAsync(0)
  await vi.advanceTimersByTimeAsync(10); f.link.invalidateCapture(); await vi.advanceTimersByTimeAsync(0)
  expect(starts).toHaveLength(1)
  await vi.advanceTimersByTimeAsync(190)
  expect(starts).toHaveLength(2); expect(starts[1] - starts[0]).toBe(200)
  f.link.dispose()
})

it.each([
  [10, 30, 'bytes-only'], [11, 30, 'bytes-with-increasing-frames'], [1, 30, 'both-counters'],
])('test_counter_rollback_advances_epoch_once_%s_%s_%s', async (frames, bytes) => {
  const f = fixture(); let count = 0
  f.adapter.readRadar = async () => ++count === 1 ? { ...payload(10), bytes: 300 } : { ...payload(frames), bytes }
  await f.link.enable(); await vi.advanceTimersByTimeAsync(200)
  expect(f.frames.map(row => row[2])).toEqual([1, 2])
  f.link.dispose()
})

it('test_reconnect_clears_both_counter_baselines', async () => {
  const f = fixture()
  f.adapter.readRadar = async () => ({ ...payload(10), bytes: 300 })
  await f.link.connect('10.0.0.2'); await vi.advanceTimersByTimeAsync(0)
  f.adapter.readRadar = async () => ({ ...payload(1), bytes: 30 })
  await f.link.connect('10.0.0.3'); await vi.advanceTimersByTimeAsync(200)
  expect(f.frames.map(row => row[2])).toEqual([1, 2])
  f.link.dispose()
})
