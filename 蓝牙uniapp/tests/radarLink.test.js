import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { createRadarLink } from '../utils/radarLink'
const payload = (frames = 1) => ({ frames, bytes: 30, age_ms: 1, stale: false, targets: [] })
const candidates = ips => ({ networkToken: 'wifi', candidates: ips.map(ip => ({ ip, frames: 1, stale: false })) })
function fixture(discover = async () => candidates(['10.0.0.2'])) {
  const states = [], frames = [], reads = []
  const adapter = { capabilities: async () => ({ supported: true, permitted: true }), wifiScope: async () => ({ networkToken: 'wifi' }), cancel: vi.fn(), readRadar: async (ip, timeout, id) => { reads.push([ip, timeout, id]); return payload() } }
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
