import { expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../uni_modules/sarcogait-radar/utssdk/app-android/index.uts', import.meta.url), 'utf8')

it('uses named UTS callback parameters that remain valid after Kotlin lowering', () => {
  const names = [...source.matchAll(/\(([^()]*)\)\s*=>/g)]
    .flatMap(match => match[1].split(','))
    .map(parameter => parameter.trim().match(/^([\w$]+)\s*:/)?.[1])
    .filter(Boolean)
  expect(names.filter(name => /^_+$/.test(name))).toEqual([])
})

// Exercise the existing permission body after removing only its UTS type syntax.
// This seam does not emulate UTS-to-Kotlin compilation or an Android runtime.
function permissionAdapter(result, response) {
  const body = source.match(/export async function capabilities\(\): Promise<RadarCapabilities> \{([\s\S]*?)\n\}/)?.[1]
  if (!body) throw new Error('capabilities body missing')
  const javascript = body
    .replace(/JSON\.parse<RadarCapabilities>/g, 'JSON.parse')
    .replace(/new Promise<boolean>/g, 'new Promise')
    .replace(/:\s*(boolean|string\[\])/g, '')
    .replace(/(?<=[\w)])!(?![=])/g, '')
  const requestSystemPermission = vi.fn((activity, permissions, success, fail) => {
    response(success, fail)
  })
  const invoke = vi.fn(async () => JSON.stringify(result))
  const bridge = { getUniActivity: () => ({}), requestSystemPermission }
  const capabilities = new Function('invoke', 'UTSAndroid',
    `let permissionRequested = false; return async function capabilities() {${javascript}}`)(invoke, bridge)
  return { capabilities, requestSystemPermission }
}

const needsPermission = {
  supported: true, permitted: false, sdk: 33, targetSdk: 33,
  permission: 'android.permission.NEARBY_WIFI_DEVICES', declared: true,
}

it('preserves the success callback result and requests the declared permission', async () => {
  const adapter = permissionAdapter(needsPermission, success => success(true, [needsPermission.permission]))
  expect((await adapter.capabilities()).permitted).toBe(true)
  expect(adapter.requestSystemPermission).toHaveBeenCalledTimes(1)
  expect(adapter.requestSystemPermission.mock.calls[0][1]).toEqual([needsPermission.permission])
})

it('keeps permission denied when the native failure callback runs', async () => {
  const adapter = permissionAdapter(needsPermission, (success, fail) => fail(true, []))
  expect((await adapter.capabilities()).permitted).toBe(false)
  expect(adapter.requestSystemPermission).toHaveBeenCalledTimes(1)
})

it('does not request permission again when the capability is already permitted', async () => {
  const adapter = permissionAdapter({ ...needsPermission, permitted: true }, () => {
    throw new Error('already-permitted capability must not request permission')
  })
  expect((await adapter.capabilities()).permitted).toBe(true)
  expect(adapter.requestSystemPermission).not.toHaveBeenCalled()
})
