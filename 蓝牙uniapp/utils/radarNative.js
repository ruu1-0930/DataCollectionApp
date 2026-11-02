import { isPrivateIPv4, parseRadarPayload } from './radarProtocol'
// Ordinary uni-app JS uses APP-PLUS; APP-ANDROID is a UTS-only symbol.
// #ifdef APP-PLUS
import * as radarPlugin from '@/uni_modules/sarcogait-radar'
// #endif
const codes = new Set(['unsupported', 'permission', 'wifi_unavailable', 'network_changed', 'network', 'timeout', 'cancelled', 'response_too_large', 'redirect', 'protocol', 'invalid_ip'])
export function createRadarNative(plugin) {
  if (!plugin) {
    // #ifdef APP-PLUS
    if (typeof uni !== 'undefined' && uni.getSystemInfoSync().platform === 'android') plugin = radarPlugin
    // #endif
  }
  const safe = async fn => { try { return await fn() } catch (e) { throw Error(codes.has(e?.message) ? e.message : codes.has(e?.code) ? e.code : 'network') } }
  return {
    capabilities: () => plugin ? safe(() => plugin.capabilities()) : Promise.resolve({ supported: false, permitted: false }),
    wifiScope: () => plugin ? safe(() => plugin.wifiScope()) : Promise.reject(Error('unsupported')),
    resolveRadarName: () => plugin ? safe(() => plugin.resolveRadarName()) : Promise.reject(Error('unsupported')),
    readRadar(ip, timeoutMs, operationId, expectedScope, subnetOnly) {
      if (!isPrivateIPv4(ip)) return Promise.reject(Error('invalid_ip'))
      if (!plugin) return Promise.reject(Error('unsupported'))
      if (!expectedScope?.networkToken || !isPrivateIPv4(expectedScope.address) || !Number.isInteger(expectedScope.prefixLength) || expectedScope.prefixLength < 0 || expectedScope.prefixLength > 32 || typeof subnetOnly !== 'boolean') return Promise.reject(Error('network_changed'))
      return safe(async () => parseRadarPayload(await plugin.readRadar(ip, Math.min(2500, Math.max(1, timeoutMs)), operationId, expectedScope, subnetOnly)))
    },
    cancel(id) { if (plugin) plugin.cancel(id) },
  }
}
