import { describe, it, expect } from 'vitest'
import { parseRadarPayload, isPrivateIPv4, visibleRadarTargets } from '../utils/radarProtocol'
const payload = () => ({ frames: 1, bytes: 30, age_ms: 10, stale: false, targets: [{ slot: 1, present: true, x_mm: -2, y_mm: 4, speed_cms: -5, resolution_mm: 0 }] })
describe('radar strict wire boundary', () => {
  it('preserves raw values and derives display validity independently', () => {
    expect(parseRadarPayload(payload())).toEqual(payload())
    expect(visibleRadarTargets(payload())).toHaveLength(1)
    for (const change of [{ frames: 0 }, { stale: true }, { age_ms: null }, { age_ms: 1501 }]) expect(visibleRadarTargets({ ...payload(), ...change })).toEqual([])
  })
  it('rejects unknown keys, coercion, duplicate slots and integer overflows', () => {
    for (const change of [{ extra: 1 }, { frames: '1' }, { age_ms: Infinity }, { bytes: -1 }, { targets: [...payload().targets, ...payload().targets] }, { targets: [{ ...payload().targets[0], speed_cms: -32768 }] }]) expect(() => parseRadarPayload({ ...payload(), ...change })).toThrow('protocol')
    expect(parseRadarPayload({ ...payload(), targets: [] }).targets).toEqual([])
  })
  it('accepts only canonical RFC1918 HTTP addresses', () => {
    for (const ip of ['10.0.0.1', '172.16.0.1', '172.31.255.254', '192.168.1.1']) expect(isPrivateIPv4(ip)).toBe(true)
    for (const ip of ['127.0.0.1', '172.32.0.1', '8.8.8.8', '192.168.001.1', 'http://10.0.0.1', '10.0.0.1:80']) expect(isPrivateIPv4(ip)).toBe(false)
  })
})
