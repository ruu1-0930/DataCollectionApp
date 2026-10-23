import { isPrivateIPv4, parseRadarPayload } from './radarProtocol'
// Conditional import keeps other targets explicit unsupported, without touching BLE.
// #ifdef APP-ANDROID
import * as radarPlugin from '@/uni_modules/sarcogait-radar'
// #endif
const codes = new Set(['unsupported', 'permission', 'wifi_unavailable', 'network_changed', 'network', 'timeout', 'cancelled', 'response_too_large', 'redirect', 'protocol', 'invalid_ip'])
export function createRadarNative(plugin) {
  if (!plugin) {
    // #ifdef APP-ANDROID
    plugin = radarPlugin
    // #endif
  }
  const safe = async fn => { try { return await fn() } catch (e) { throw Error(codes.has(e?.message) ? e.message : codes.has(e?.code) ? e.code : 'network') } }
  return {
    capabilities: () => plugin ? safe(() => plugin.capabilities()) : Promise.resolve({ supported: false, permitted: false }),
    wifiScope: () => plugin ? safe(() => plugin.wifiScope()) : Promise.reject(Error('unsupported')),
    resolveRadarName: () => plugin ? safe(() => plugin.resolveRadarName()) : Promise.reject(Error('unsupported')),
    readRadar(ip, timeoutMs, operationId) {
      if (!isPrivateIPv4(ip)) return Promise.reject(Error('invalid_ip'))
      if (!plugin) return Promise.reject(Error('unsupported'))
      return safe(async () => parseRadarPayload(await plugin.readRadar(ip, Math.min(2500, Math.max(1, timeoutMs)), operationId)))
    },
    cancel(id) { if (plugin) plugin.cancel(id) },
  }
}
