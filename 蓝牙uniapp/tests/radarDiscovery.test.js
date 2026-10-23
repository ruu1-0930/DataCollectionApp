import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { createRadarDiscovery } from '../utils/radarDiscovery'
import { readFileSync } from 'node:fs'
import { parseRadarPayload, isPrivateIPv4 } from '../utils/radarProtocol'
const payload = { frames: 1, bytes: 30, age_ms: 1, stale: false, targets: [] }
function fixture({ names = [], cached, permission = true, address = '192.168.3.4', prefixLength = 24, read } = {}) {
  const calls = [], writes = []
  let token = 'wifi-1'
  const adapter = { capabilities: async () => ({ supported: true, permitted: permission }), wifiScope: async () => ({ networkToken: token, address, prefixLength }),
    resolveRadarName: async () => { calls.push('name'); return names },
    readRadar: async (ip, timeout, id) => { calls.push([ip, timeout, id]); if (read) return read(ip); throw Error('network') }, cancel: vi.fn() }
  const discovery = createRadarDiscovery({ adapter, cache: { get: () => cached, set: (network, ip) => writes.push([network, ip]) } })
  return { discovery, calls, writes, adapter, token: value => { token = value } }
}
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())
it('test_name_only_mdns_without_dns_sd', async () => {
  const f = fixture({ names: ['192.168.3.9'], read: async () => payload })
  expect((await f.discovery.discover()).candidates).toEqual([{ ip: '192.168.3.9', frames: 1, stale: false }])
  expect(f.calls.map(v => typeof v === 'string' ? v : v[0])).toEqual(['name', '192.168.3.9'])
})
it('test_name_cache_subnet_order', async () => {
  const f = fixture({ names: ['192.168.3.9'], cached: '192.168.3.8', prefixLength: 30 })
  await f.discovery.discover()
  expect(f.calls.map(v => typeof v === 'string' ? v : v[0])).toEqual(['name', '192.168.3.9', '192.168.3.8', '192.168.3.5', '192.168.3.6'])
  expect(f.writes).toEqual([])
})
it('test_discovery_limits', async () => {
  let active = 0, maximum = 0
  const f = fixture({ address: '10.2.3.1', prefixLength: 16, read: () => new Promise((_, reject) => { maximum = Math.max(maximum, ++active); setTimeout(() => { active--; reject(Error('network')) }, 500) }) })
  const done = f.discovery.discover()
  await vi.runAllTimersAsync(); await done
  expect(maximum).toBeLessThanOrEqual(8)
  expect(f.calls.filter(Array.isArray).length).toBeLessThanOrEqual(254)
  expect(f.calls.filter(Array.isArray).every(c => c[1] === 500 && c[0].startsWith('10.2.3.'))).toBe(true)
})
it('test_permission_denial_never_starts_scan', async () => {
  const f = fixture({ permission: false })
  await expect(f.discovery.discover()).rejects.toThrow('permission')
  expect(f.calls).toEqual([])
})
it('test_network_change_invalidates_late_response', async () => {
  let finish
  const f = fixture({ names: ['192.168.3.9'], read: () => new Promise(resolve => { finish = resolve }) })
  const pending = f.discovery.discover(); await vi.advanceTimersByTimeAsync(0)
  f.token('wifi-2'); finish(payload)
  await expect(pending).rejects.toThrow('network_changed')
  expect(f.writes).toEqual([])
})
it('ends a discovery round at 30 seconds even if name resolution never replies', async () => {
  const f = fixture()
  f.adapter.resolveRadarName = () => new Promise(() => {})
  const outcome = f.discovery.discover().catch(e => e.message)
  await vi.advanceTimersByTimeAsync(30000)
  expect(await outcome).toBe('discovery_timeout')
  expect(f.calls).toEqual([])
})
it('cancels in-flight probes and rejects late candidates', async () => {
  const f = fixture({ names: ['192.168.3.9'], read: () => new Promise(() => {}) })
  const outcome = f.discovery.discover().catch(e => e.message)
  await vi.advanceTimersByTimeAsync(0); f.discovery.cancel()
  expect(await outcome).toBe('cancelled')
  expect(f.adapter.cancel.mock.calls.some(([id]) => id.startsWith('radar-discovery-'))).toBe(true)
  expect(f.writes).toEqual([])
})
it.each(['timeout', 'cancelled'])('test_native_probe_%s_does_not_cancel_discovery_round', async code => {
  // Exercise the real JS/native error boundary. Kotlin compilation remains a
  // separate gate; only the external native callback is replaced here.
  const source = readFileSync(new URL('../utils/radarNative.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
  const factory = new Function('parseRadarPayload', 'isPrivateIPv4', source + '\nreturn createRadarNative;')(parseRadarPayload, isPrivateIPv4)
  const probed = []
  const native = factory({
    readRadar: async ip => {
      probed.push(ip)
      if (ip === '10.1.2.20') return JSON.stringify(payload)
      await new Promise(resolve => setTimeout(resolve, 500))
      throw Error(code)
    },
    cancel() {},
  })
  const f = fixture({ address: '10.1.2.1', prefixLength: 24 })
  f.adapter.readRadar = native.readRadar
  const result = f.discovery.discover().catch(e => ({ error: e.message }))
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ candidates: [{ ip: '10.1.2.20', frames: 1, stale: false }] })
  expect(probed).toContain('10.1.2.20')
  expect(probed.length).toBeLessThanOrEqual(254)
})
