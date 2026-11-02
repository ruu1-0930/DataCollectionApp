import { assertCollectionIdentity } from './collectionSession'
import { createTelemetryOutbox } from './telemetryQueue'
const copy = value => JSON.parse(JSON.stringify(value))
const lanes = ['primary', 'radar']
const laneOf = stream => stream === 'radar' ? 'radar' : ['insole', 'gps'].includes(stream) ? 'primary' : null
const receiptError = () => Object.assign(Error('receipt'), { statusCode: 422 })
const statusOf = e => e?.statusCode ?? e?.data?.code
const transient = e => { const status = e?.statusCode ?? e?.data?.code; return status ? status >= 500 && status <= 599 : /request:fail|timeout|network/i.test(e?.errMsg || e?.message || '') }
const timestamp = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value))
const latestTimestamp = values => values.reduce((latest, value) => timestamp(value) && (!latest || value > latest) ? value : latest, undefined)
export function createCollectionCoordinator({ load, save, identity, api, clock = Date.now, wait = ms => new Promise(r => setTimeout(r, ms)), onChange = () => {} }) {
  let state = { version: 2, sessions: [] }, inFlight = null, halted = false, storageBroken = false, unreadable = false, error = ''
  const paused = new Set(), retries = new Map()
  let wake = null
  const wakeRun = () => { if (wake) wake(); wake = null }
  const pending = lane => state.sessions.reduce((n, s) => n + s.outboxes[lane].length, 0)
  function snapshot() {
    const originalPending = pending('primary'), radarPending = pending('radar')
    return { pending: originalPending + radarPending, originalPending, radarPending, sessions: state.sessions.length, sending: !!inFlight,
      paused: halted || paused.size > 0, error, radarPaused: [...paused].some(k => k.endsWith(':radar')), primaryPaused: [...paused].some(k => k.endsWith(':primary')) }
  }
  const publish = () => onChange(snapshot())
  function persist(next) {
    try { save(JSON.stringify(next)); state = next; storageBroken = false }
    catch { storageBroken = true; halted = true; error = 'storage'; publish(); throw Error('storage') }
    publish()
  }
  function validate(restored) {
    if (![1, 2].includes(restored?.version) || !Array.isArray(restored.sessions) || restored.sessions.length > 100) throw Error('storage')
    const captures = new Set()
    for (const s of restored.sessions) {
      if (!s || typeof s.capture_id !== 'string' || !s.capture_id || captures.has(s.capture_id) || !s.clinicianId || !s.patient_id || !s.device_code || !timestamp(s.mobile_started_at) ||
        typeof s.created !== 'boolean' || !(s.mobile_stopped_at === null || timestamp(s.mobile_stopped_at))) throw Error('storage')
      captures.add(s.capture_id)
      const outboxes = restored.version === 1 ? { primary: s.events, radar: [] } : s.outboxes
      if (!outboxes || !lanes.every(l => Array.isArray(outboxes[l]))) throw Error('storage')
      const ids = new Set()
      for (const lane of lanes) for (const e of outboxes[lane]) {
        if (!e || !e.event_id || ids.has(e.event_id) || laneOf(e.stream) !== lane || !timestamp(e.mobile_received_at)) throw Error('storage')
        ids.add(e.event_id)
      }
    }
    for (const lane of lanes) if (restored.sessions.reduce((n, s) => n + (restored.version === 1 ? lane === 'primary' ? s.events.length : 0 : s.outboxes[lane].length), 0) > 5000) throw Error('storage')
  }
  try {
    const saved = load()
    if (saved) {
      const restored = JSON.parse(saved); validate(restored)
      let next = copy(restored), changed = restored.version === 1
      if (changed) next = { version: 2, sessions: restored.sessions.map(({ events, ...s }) => ({ ...s, outboxes: { primary: copy(events), radar: [] } })) }
      for (const s of next.sessions) if (!s.mobile_stopped_at) {
        const stamps = [s.mobile_started_at, s.last_received_at]
        for (const lane of lanes) for (const event of s.outboxes[lane]) stamps.push(event.mobile_received_at)
        s.mobile_stopped_at = latestTimestamp(stamps)
        changed = true
      }
      if (changed) {
        try { persist(next) }
        catch {
          // Failed migration must preserve v1 bytes and never send. A readable v2
          // freeze is retained in memory so manual retry can persist it first.
          if (restored.version === 1) unreadable = true
          else state = next
        }
      } else state = next
    }
  } catch { unreadable = true; storageBroken = true; halted = true; error = 'storage' }
  function assertActor(session, binding) {
    const actor = identity()
    if (session.clinicianId !== actor.clinicianId) throw Object.assign(Error('identity'), { statusCode: 403 })
    assertCollectionIdentity({ collectionIdentity: binding }, actor)
  }
  async function send(operation, session, binding) {
    assertActor(session, binding)
    const result = await operation(); assertActor(session, binding); return result
  }
  const find = id => state.sessions.find(s => s.capture_id === id)
  function update(id, mutation) { const next = copy(state), s = next.sessions.find(s => s.capture_id === id); if (s) mutation(s, next); persist(next) }
  async function step(id, lane, binding) {
    const session = find(id)
    if (!session) return false
    const kind = !session.created ? 'create' : session.outboxes[lane].length ? lane : 'stop', key = `${id}:${kind}`
    if (kind === 'stop' && (!session.mobile_stopped_at || lanes.some(l => session.outboxes[l].length))) return false
    if (paused.has(key) || paused.has(`${id}:create`) || retries.has(key) && !retries.get(key).ready) return false
    assertActor(session, binding)
    try {
      if (!session.created) {
        const { capture_id, patient_id, device_code, mobile_started_at } = session
        const result = await send(() => api.create({ capture_id, patient_id, device_code, mobile_started_at }, binding), session, binding)
        if (result?.capture_id !== id) throw receiptError()
        update(id, s => { s.created = true }); retries.delete(key); return true
      }
      if (session.outboxes[lane].length) {
        const events = createTelemetryOutbox({ events: session.outboxes[lane] }).peekBatch()
        if (!events.length) throw receiptError()
        const result = await send(() => api.batch(id, { events }, binding), session, binding)
        if (result?.capture_id !== id || !Array.isArray(result.results) || result.results.length !== events.length) throw receiptError()
        const ids = new Set()
        for (const r of result.results) {
          if (!events.some(e => e.event_id === r.event_id && e.stream === r.stream) || ids.has(r.event_id) || !['accepted', 'duplicate'].includes(r.status) || !timestamp(r.server_received_at)) throw receiptError()
          ids.add(r.event_id)
        }
        update(id, s => { const box = createTelemetryOutbox({ events: s.outboxes[lane] }); box.ack(ids); s.outboxes[lane] = box.snapshot() }); retries.delete(key); return true
      }
      if (session.mobile_stopped_at && lanes.every(l => !session.outboxes[l].length) && !paused.has(`${id}:stop`)) {
        const result = await send(() => api.stop(id, { mobile_stopped_at: session.mobile_stopped_at }, binding), session, binding)
        if (result?.capture_id !== id) throw receiptError()
        update(id, (_, next) => { next.sessions = next.sessions.filter(s => s.capture_id !== id) }); retries.delete(key); return true
      }
      return false
    } catch (cause) {
      if (cause.message === 'storage' || [401, 403].includes(statusOf(cause))) throw cause
      const attempt = retries.get(key)?.attempt || 0
      if (transient(cause) && attempt < 3) {
        const retry = { attempt: attempt + 1, ready: false, since: clock(), done: null }
        retry.done = Promise.resolve(wait(1000 * 2 ** attempt)).then(() => { retry.ready = true; wakeRun() })
        retries.set(key, retry)
        return false
      }
      retries.delete(key); paused.add(key)
      error = 'upload'; publish(); return false
    }
  }
  async function run() {
    const binding = { ...identity() }
    // A bounded batch per lane/capture/round: old streams first; radar cannot starve.
    while (!halted) {
      let progress = false; const ids = state.sessions.map(s => s.capture_id)
      for (const lane of lanes) for (const id of ids) { if (halted) return; if (await step(id, lane, binding)) progress = true }
      if (progress) continue
      const waiting = [...retries.values()].filter(r => !r.ready)
      if ([...retries.values()].some(r => r.ready)) continue
      if (!waiting.length) break
      // A failed radar lane sleeps independently; enqueue wakes priority work now.
      const arrival = new Promise(resolve => { wake = resolve })
      await Promise.race([arrival, ...waiting.map(r => r.done)]); wake = null
    }
  }
  return {
    snapshot,
    add(context) {
      if (storageBroken || unreadable) throw Error('storage')
      if (state.sessions.length >= 100 || pending('primary') >= 5000) throw Error('capacity')
      if (find(context.capture_id)) throw Error('capture_exists')
      const { authEpoch, ...durable } = context
      const next = copy(state); next.sessions.push({ ...durable, created: false, mobile_stopped_at: null, last_received_at: context.mobile_started_at, outboxes: { primary: [], radar: [] } }); persist(next)
      wakeRun()
    },
    enqueue(captureId, event) {
      if (storageBroken || unreadable) throw Error('storage')
      const lane = laneOf(event.stream); if (!lane) throw Error('stream')
      if (pending(lane) >= 5000) throw Error('capacity')
      const s = find(captureId); if (!s || s.mobile_stopped_at) throw Error('closed')
      update(captureId, session => { const box = createTelemetryOutbox({ events: session.outboxes[lane] }); box.enqueue(event); session.outboxes[lane] = box.snapshot(); session.last_received_at = latestTimestamp([session.last_received_at, event.mobile_received_at]) })
      wakeRun()
    },
    stop(captureId, stamp) {
      const session = find(captureId); if (!session || session.mobile_stopped_at) return
      const next = copy(state), s = next.sessions.find(s => s.capture_id === captureId)
      s.mobile_stopped_at = latestTimestamp([stamp, s.last_received_at, s.mobile_started_at])
      try { persist(next) } catch (e) { state = next; throw e }
      wakeRun()
    },
    drain(manual = false) {
      if (inFlight) return inFlight
      if (unreadable || halted && !manual) return Promise.resolve()
      if (manual) {
        try { if (storageBroken) persist(state) } catch { return Promise.resolve() }
        halted = false; paused.clear(); retries.clear(); error = ''
      }
      inFlight = Promise.resolve().then(run).catch(cause => { halted = true; error = cause.message === 'storage' ? 'storage' : [401, 403].includes(statusOf(cause)) ? 'identity' : 'upload' }).finally(() => { inFlight = null; wake = null; publish() })
      publish(); return inFlight
    },
  }
}
