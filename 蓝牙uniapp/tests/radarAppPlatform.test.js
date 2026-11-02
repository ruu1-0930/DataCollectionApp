import { it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parseRadarPayload, isPrivateIPv4 } from '../utils/radarProtocol'

// Ordinary uni-app JS uses APP-PLUS for both mobile platforms. APP-ANDROID is
// only a UTS symbol here; this seam is not an HBuilderX or native build test.
function appAdapter(platform, plugin) {
  const source = readFileSync(new URL('../utils/radarNative.js', import.meta.url), 'utf8')
    .replace(/^[ \t]*\/\/ #ifdef ([\w-]+)\r?\n([\s\S]*?)^[ \t]*\/\/ #endif/gm,
      (_, symbol, body) => symbol === 'APP-PLUS' && platform !== 'web' ? body : '')
    .replace(/^import .*$/gm, '').replace(/export /g, '')
  return new Function('parseRadarPayload', 'isPrivateIPv4', 'radarPlugin', 'uni',
    source + '\nreturn createRadarNative();')(parseRadarPayload, isPrivateIPv4, plugin,
    { getSystemInfoSync: () => ({ platform }) })
}

it('loads the radar plugin in an ordinary Android uni-app build', async () => {
  const capabilities = vi.fn(async () => ({ supported: true, permitted: true }))
  const adapter = appAdapter('android', { capabilities })
  expect(await adapter.capabilities()).toEqual({ supported: true, permitted: true })
  expect(capabilities).toHaveBeenCalledTimes(1)
})

it.each(['ios', 'web'])('keeps %s explicitly unsupported without calling the Android plugin', async platform => {
  const capabilities = vi.fn(async () => ({ supported: true, permitted: true }))
  expect(await appAdapter(platform, { capabilities }).capabilities()).toEqual({ supported: false, permitted: false })
  expect(capabilities).not.toHaveBeenCalled()
})
