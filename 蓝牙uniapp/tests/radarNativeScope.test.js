import { it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parseRadarPayload, isPrivateIPv4 } from '../utils/radarProtocol'
const source = readFileSync(new URL('../utils/radarNative.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
const factory = new Function('parseRadarPayload', 'isPrivateIPv4', source + '\nreturn createRadarNative;')(parseRadarPayload, isPrivateIPv4)
const scope = { networkToken: 'wifi-A', address: '10.1.2.1', prefixLength: 24 }
const payload = JSON.stringify({ frames: 1, bytes: 30, age_ms: 1, stale: false, targets: [] })

it('test_private_native_wrapper_forwards_scope_and_discovery_mode_with_timeout_cap', async () => {
  const readRadar = vi.fn(async () => payload), native = factory({ readRadar })
  await native.readRadar('10.1.2.2', 9999, 'scope-test', scope, true)
  expect(readRadar.mock.calls).toEqual([['10.1.2.2', 2500, 'scope-test', scope, true]])
})

it('test_private_native_wrapper_does_not_start_unscoped_http', async () => {
  const readRadar = vi.fn(async () => payload), native = factory({ readRadar })
  await expect(native.readRadar('10.1.2.2', 500, 'scope-test')).rejects.toThrow('network_changed')
  expect(readRadar).not.toHaveBeenCalled()
})
