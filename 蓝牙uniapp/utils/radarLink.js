import { isPrivateIPv4, parseRadarPayload } from './radarProtocol'
import { sameRadarScope } from './radarDiscovery'
let serial = 0
export function createRadarLink({ discovery, adapter, clock = Date.now, timers = globalThis, onFrame = () => {}, onState = () => {}, captureContext = () => null }) {
  let enabled = false, foreground = true, disposed = false, generation = 0, timer = null, operation = null, release = null
  let epoch = 0, ip = null, networkToken = null, expectedScope = null, previousFrames = null, previousBytes = null, failures = 0, lastDiscovery = -Infinity
  let lastPollStarted = -Infinity
  const state = (status, extra = {}) => onState({ status, enabled, ip, epoch, networkToken, ...extra })
  function cancelWork() {
    generation++; timers.clearTimeout(timer); timer = null; discovery.cancel()
    if (operation) adapter.cancel(operation)
    if (release) release()
    operation = null; release = null
  }
  const valid = token => !disposed && enabled && foreground && token === generation
  function later(fn, ms, token) { timers.clearTimeout(timer); if (valid(token)) timer = timers.setTimeout(() => { if (valid(token)) fn() }, ms) }
  async function rediscover(token) {
    if (!valid(token)) return
    const delay = Math.max(0, lastDiscovery + 30000 - clock())
    if (delay) { state('retry_wait'); later(() => rediscover(token), delay, token); return }
    lastDiscovery = clock(); state('discovering')
    try {
      const found = await discovery.discover()
      if (!valid(token)) return
      if (found.candidates.length === 1) await connect(found.candidates[0].ip)
      else if (found.candidates.length > 1) state('selection', { candidates: found.candidates })
      else { state('not_found'); later(() => rediscover(token), 30000, token) }
    } catch (e) {
      if (!valid(token)) return
      state(e.message)
      if (!['permission', 'unsupported'].includes(e.message)) later(() => rediscover(token), 30000, token)
    }
  }
  async function poll(token) {
    if (!valid(token)) return
    const delay = Math.max(0, lastPollStarted + 200 - clock())
    if (delay) { later(() => poll(token), delay, token); return }
    lastPollStarted = clock()
    const began = clock(), id = `radar-poll-${++serial}`, context = captureContext()
    operation = id
    let timeout
    try {
      const scope = await adapter.wifiScope()
      if (!valid(token)) return
      if (!sameRadarScope(scope, expectedScope)) throw Error('network_changed')
      const guard = new Promise((_, reject) => { release = () => reject(Error('cancelled')); timeout = timers.setTimeout(() => { adapter.cancel(id); reject(Error('network')) }, 2500) })
      const raw = await Promise.race([adapter.readRadar(ip, 2500, id, expectedScope, false), guard])
      if (!valid(token)) return
      const current = await adapter.wifiScope()
      if (!valid(token)) return
      if (!sameRadarScope(current, expectedScope)) throw Error('network_changed')
      const payload = parseRadarPayload(raw), receivedAt = clock()
      if ((previousFrames !== null && payload.frames < previousFrames) || (previousBytes !== null && payload.bytes < previousBytes)) epoch++
      previousFrames = payload.frames; previousBytes = payload.bytes; failures = 0
      state('connected'); onFrame(payload, receivedAt, epoch, networkToken, context)
    } catch (e) {
      if (!valid(token)) return
      if (['permission', 'unsupported'].includes(e.message)) { state(e.message); return }
      if (e.message !== 'network_changed') {
        try {
          const current = await adapter.wifiScope()
          if (!valid(token)) return
          if (!sameRadarScope(current, expectedScope)) e = Error('network_changed')
        } catch (scopeError) {
          if (!valid(token)) return
          if (scopeError.message === 'permission') { state('permission'); return }
          e = Error('network_changed')
        }
      }
      if (e.message === 'network_changed') { adapter.cancel(id); epoch++; ip = null; expectedScope = null; state('network_changed'); later(() => rediscover(token), 0, token); return }
      if (e.message === 'protocol') { failures = 0; state('protocol') }
      else { failures++; state('network', { failures }) }
      if (failures >= 3) { later(() => rediscover(token), 0, token); return }
    } finally {
      timers.clearTimeout(timeout)
      if (operation === id) { operation = null; release = null }
    }
    later(() => poll(token), Math.max(200 - (clock() - began), failures ? Math.min(30000, 200 * 2 ** failures) : 0), token)
  }
  async function connect(address) {
    cancelWork()
    if (!isPrivateIPv4(address)) { state('invalid_ip'); return }
    if (disposed || !foreground) return
    enabled = true
    const token = generation
    try {
      const cap = await adapter.capabilities()
      if (!valid(token)) return
      if (!cap.supported || !cap.permitted) { state(cap.supported ? 'permission' : 'unsupported'); return }
      const scope = await adapter.wifiScope()
      if (!valid(token)) return
      if (!scope.networkToken) { state('wifi_unavailable'); return }
      ip = address; networkToken = scope.networkToken; expectedScope = { ...scope }; epoch++; failures = 0; previousFrames = null; previousBytes = null
      state('connecting'); later(() => poll(token), 0, token)
    } catch (e) { if (valid(token)) state(e.message || 'network') }
  }
  return {
    enable() { if (disposed) return Promise.resolve(); cancelWork(); enabled = true; return foreground ? rediscover(generation) : Promise.resolve() },
    connect,
    disconnect() { enabled = false; cancelWork(); ip = null; state('paused') },
    invalidateCapture() {
      // Discovery/selection has no capture binding yet. Retire only a poll which
      // already froze a capture token; do not restart after permission denial.
      if (!operation) return
      cancelWork()
      if (enabled && foreground && !disposed && ip && networkToken) later(() => poll(generation), 0, generation)
    },
    setForeground(value) { if (foreground === value) return; foreground = value; cancelWork(); epoch++; state(value ? 'idle' : 'background'); if (value && enabled) rediscover(generation) },
    dispose() { disposed = true; enabled = false; cancelWork(); state('disposed') },
  }
}
