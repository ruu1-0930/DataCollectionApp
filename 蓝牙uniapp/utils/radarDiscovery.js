import { isPrivateIPv4, parseRadarPayload } from './radarProtocol'
let serial = 0
const asNumber = ip => ip.split('.').reduce((a, b) => (a * 256 + Number(b)) >>> 0, 0)
const asIP = n => [24, 16, 8, 0].map(s => (n >>> s) & 255).join('.')
export function radarSubnet(scope) {
  if (!isPrivateIPv4(scope?.address) || !Number.isInteger(scope.prefixLength) || scope.prefixLength < 1 || scope.prefixLength > 30) return []
  const local = asNumber(scope.address), mask = (0xffffffff << (32 - scope.prefixLength)) >>> 0
  const first = Math.max((local & mask) >>> 0, (local & 0xffffff00) >>> 0)
  const last = Math.min(((local & mask) | ~mask) >>> 0, ((local & 0xffffff00) | 255) >>> 0)
  const out = []
  for (let n = first + 1; n < last && out.length < 254; n++) if (n !== local && isPrivateIPv4(asIP(n))) out.push(asIP(n))
  return out
}
export function createRadarDiscovery({ adapter, clock = Date.now, timers = globalThis, cache = {}, onState = () => {} }) {
  let generation = 0, currentCancel = null
  function cancel() { generation++; if (currentCancel) currentCancel() }
  async function discover() {
    cancel()
    const own = generation, ids = new Set(), deadline = clock() + 30000
    let expired = false, expire
    const timeout = new Promise(resolve => { expire = resolve })
    const stop = () => { expired = true; ids.forEach(id => adapter.cancel(id)); adapter.cancel('radar-name'); expire({ cancelled: true }) }
    currentCancel = stop
    const timer = timers.setTimeout(stop, 30000)
    const valid = () => own === generation && !expired && clock() < deadline
    const guard = () => { if (!valid()) throw Error('cancelled') }
    async function work() {
      const cap = await adapter.capabilities(); guard()
      if (!cap.supported) throw Error('unsupported')
      if (!cap.permitted) throw Error('permission')
      const scope = await adapter.wifiScope(); guard()
      if (!scope?.networkToken) throw Error('wifi_unavailable')
      const seen = new Set(), candidates = []
      async function probe(ip) {
        if (!valid() || !isPrivateIPv4(ip) || seen.has(ip) || seen.size >= 254) return
        seen.add(ip)
        const id = `radar-discovery-${++serial}`; ids.add(id)
        try {
          const result = await adapter.readRadar(ip, Math.min(500, Math.max(1, deadline - clock())), id); guard()
          const current = await adapter.wifiScope(); guard()
          if (current.networkToken !== scope.networkToken) throw Error('network_changed')
          const p = parseRadarPayload(result)
          candidates.push({ ip, frames: p.frames, stale: p.stale })
          if (cache.set) cache.set(scope.networkToken, ip)
        } catch (e) {
          // Whole-round cancellation belongs to this controller's generation and
          // deadline. An adapter-cancelled/expired probe must not retire its peers.
          if (e.message === 'network_changed' || e.message === 'permission') throw e
        }
        finally { ids.delete(id) }
      }
      onState({ status: 'discovering' })
      let names = []
      try { names = await adapter.resolveRadarName() } catch (e) { if (e.message === 'permission') throw e }
      guard()
      for (const ip of (Array.isArray(names) ? names : []).slice(0, 8)) await probe(ip)
      if (!candidates.length && cache.get) await probe(cache.get(scope.networkToken))
      if (!candidates.length) {
        const addresses = radarSubnet(scope)
        let index = 0
        await Promise.all(Array.from({ length: Math.min(8, addresses.length) }, async () => {
          while (valid() && index < addresses.length) await probe(addresses[index++])
        }))
      }
      guard()
      return { candidates, networkToken: scope.networkToken }
    }
    try {
      const result = await Promise.race([work(), timeout])
      if (result.cancelled) throw Error(own !== generation ? 'cancelled' : 'discovery_timeout')
      onState({ status: result.candidates.length ? 'discovered' : 'not_found', ...result })
      return result
    } finally { timers.clearTimeout(timer); stop(); if (own === generation) currentCancel = null }
  }
  return { discover, cancel }
}
