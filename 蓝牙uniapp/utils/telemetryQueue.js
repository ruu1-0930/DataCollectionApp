import { assertCollectionIdentity } from './collectionSession'

const copy = value => JSON.parse(JSON.stringify(value))
const waitDefault = ms => new Promise(resolve => setTimeout(resolve, ms))
const transient = error => {
  const status = error?.statusCode ?? error?.data?.code
  return status ? status >= 500 && status <= 599 : /request:fail|timeout|network/i.test(error?.errMsg || error?.message || '')
}
function receiptError() { const error = new Error('receipt'); error.statusCode = 422; return error }

export function createTelemetryQueue({ load, save, identity, api, wait = waitDefault, onChange = () => {} }) {
  let state = { version: 1, sessions: [] }, inFlight = null, halted = false, error = '', storageBroken = false, unreadable = false
  function snapshot() { return { pending: state.sessions.reduce((n, s) => n + s.events.length, 0), sessions: state.sessions.length,
    sending: !!inFlight, paused: halted, error } }
  const publish = () => onChange(snapshot())
  function persist(next) {
    try { save(JSON.stringify(next)); state = next; storageBroken = false }
    catch { storageBroken = true; halted = true; error = 'storage'; publish(); throw new Error('storage') }
    publish()
  }
  try {
    const saved = load()
    if (saved) {
      const restored = JSON.parse(saved)
      if (restored?.version !== 1 || !Array.isArray(restored.sessions) || restored.sessions.length > 100 ||
          restored.sessions.some(s => !s || !s.capture_id || !s.clinicianId || !Array.isArray(s.events)) ||
          restored.sessions.reduce((n, s) => n + s.events.length, 0) > 5000) throw new Error('storage')
      state = restored
    }
  } catch { unreadable = true; storageBroken = true; halted = true; error = 'storage'; publish() }
  if (!unreadable && state.sessions.some(s => !s.mobile_stopped_at)) {
    // A process restart never resumes recording silently. Only the durable window is closed.
    for (const s of state.sessions) if (!s.mobile_stopped_at) s.mobile_stopped_at = s.last_received_at || s.mobile_started_at
    try { persist(state) } catch { /* Retain the closed window in memory for manual retry. */ }
  }

  function assertActor(session, binding) {
    const actor = identity()
    if (session.clinicianId !== actor.clinicianId) throw Object.assign(new Error('identity'), { statusCode: 403 })
    assertCollectionIdentity({ collectionIdentity: binding }, actor)
  }
  async function send(operation, session, binding) {
    for (let retries = 0; ; retries++) {
      assertActor(session, binding)
      try { const result = await operation(); assertActor(session, binding); return result }
      catch (cause) {
        if (retries >= 3 || !transient(cause)) throw cause
        await wait(1000 * 2 ** retries)
      }
    }
  }
  async function run() {
    const binding = { ...identity() }
    while (state.sessions.length) {
      const session = state.sessions[0]
      assertActor(session, binding)
      if (!session.created) {
        const { capture_id, patient_id, device_code, mobile_started_at } = session
        const result = await send(() => api.create({ capture_id, patient_id, device_code, mobile_started_at }, binding), session, binding)
        if (result?.capture_id !== capture_id) throw receiptError()
        const next = copy(state); next.sessions[0].created = true; persist(next)
      } else if (session.events.length) {
        const stream = session.events[0].stream, events = []
        for (const event of session.events) {
          if (events.length === 50 || event.stream !== stream) break
          // Three bytes per UTF-16 code unit is a conservative UTF-8 upper bound.
          if (JSON.stringify({ events: [...events, event] }).length * 3 > 128 * 1024) break
          events.push(copy(event))
        }
        if (!events.length) throw receiptError()
        const result = await send(() => api.batch(session.capture_id, { events }, binding), session, binding)
        if (result?.capture_id !== session.capture_id || !Array.isArray(result.results) || result.results.length !== events.length) throw receiptError()
        const ids = new Set()
        for (const item of result.results) {
          if (!events.some(e => e.event_id === item.event_id && e.stream === item.stream) ||
              !['accepted', 'duplicate'].includes(item.status) || ids.has(item.event_id) ||
              !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(item.server_received_at || '')) throw receiptError()
          ids.add(item.event_id)
        }
        const next = copy(state); next.sessions[0].events = next.sessions[0].events.filter(e => !ids.has(e.event_id)); persist(next)
      } else if (session.mobile_stopped_at) {
        const result = await send(() => api.stop(session.capture_id, { mobile_stopped_at: session.mobile_stopped_at }, binding), session, binding)
        if (result?.capture_id !== session.capture_id) throw receiptError()
        const next = copy(state); next.sessions.shift(); persist(next)
      } else break
    }
  }
  return {
    snapshot,
    add(context) {
      if (storageBroken) throw new Error('storage')
      if (state.sessions.length >= 100 || snapshot().pending >= 5000) throw new Error('capacity')
      const next = copy(state)
      const { authEpoch, ...durable } = context
      next.sessions.push({ ...durable, events: [], created: false, mobile_stopped_at: null, last_received_at: context.mobile_started_at })
      persist(next)
    },
    enqueue(captureId, event) {
      if (storageBroken) throw new Error('storage')
      if (snapshot().pending >= 5000) throw new Error('capacity')
      const next = copy(state), session = next.sessions.find(s => s.capture_id === captureId)
      if (!session || session.mobile_stopped_at) throw new Error('closed')
      session.events.push(copy(event)); session.last_received_at = event.mobile_received_at
      persist(next)
    },
    stop(captureId, stamp) {
      const next = copy(state), session = next.sessions.find(s => s.capture_id === captureId)
      if (!session || session.mobile_stopped_at) return
      session.mobile_stopped_at = stamp
      // Keep an unsaved stop in memory for an explicit storage recovery attempt.
      try { persist(next) } catch (cause) { state = next; throw cause }
    },
    drain(manual = false) {
      if (inFlight) return inFlight
      if (unreadable) return Promise.resolve()
      if (halted && !manual) return Promise.resolve()
      if (manual) {
        try { if (storageBroken) persist(state) } catch { return Promise.resolve() }
        halted = false; error = ''
      }
      inFlight = Promise.resolve().then(run).catch(cause => {
        halted = true
        error = cause?.message === 'storage' ? 'storage' : cause?.statusCode === 403 ? 'identity' : 'upload'
      }).finally(() => { inFlight = null; publish() })
      publish()
      return inFlight
    },
  }
}
