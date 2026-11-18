import { assertCollectionIdentity } from './collectionSession'
import { COLLECTION_TEST_TYPES } from './collectionRegistration'
import { createTelemetryOutbox } from './telemetryQueue'
const copy = value => JSON.parse(JSON.stringify(value))
const lanes = ['primary', 'radar']
const streams = ['insole', 'gps', 'radar']
const uploadKinds = ['create', ...lanes, 'stop']
const qualityObservations = new Set(['no_insole_frames', 'gps_contains_no_fix', 'radar_contains_stale'])
const completionLimit = 20
const emptyCounts = () => ({ insole: 0, gps: 0, radar: 0 })
const laneOf = stream => stream === 'radar' ? 'radar' : ['insole', 'gps'].includes(stream) ? 'primary' : null
const receiptError = () => Object.assign(Error('receipt'), { statusCode: 422 })
const statusOf = e => e?.statusCode ?? e?.data?.code
const transient = e => { const status = e?.statusCode ?? e?.data?.code; return status ? status >= 500 && status <= 599 : /request:fail|timeout|network/i.test(e?.errMsg || e?.message || '') }
const timestamp = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value))
const observationTime = value => timestamp(value) && !value.startsWith('0000-') && new Date(value).toISOString() === value
const latestTimestamp = values => values.reduce((latest, value) => timestamp(value) && (!latest || value > latest) ? value : latest, undefined)
const exact = (value, keys) => value && typeof value === 'object' && Object.keys(value).length === keys.length && keys.every(key => Object.prototype.hasOwnProperty.call(value, key))
const countsValid = value => exact(value, streams) && streams.every(stream => Number.isSafeInteger(value[stream]) && value[stream] >= 0)
const countsEqual = (a, b) => streams.every(stream => a[stream] === b[stream])
const knownType = value => COLLECTION_TEST_TYPES.some(type => type.code === value)
const registrationBound = (value, patientId) => value?.schema_version === 1 && value.patient_id === patientId
  && !!value.patient_snapshot && knownType(value.test_type)

function validVerification(value, id, expected) {
  const fields = ['record_id', 'record_version', 'observed_at', 'expected_counts', 'received_counts', 'upload_state', 'quality_observations']
  if (!exact(value, fields) || value.record_id !== id || typeof value.record_version !== 'string' || !/^[a-f0-9]{64}$/.test(value.record_version)
    || !observationTime(value.observed_at) || !countsValid(value.expected_counts) || !countsValid(value.received_counts)
    || !Array.isArray(value.quality_observations) || value.quality_observations.some(observation => !qualityObservations.has(observation))
    || new Set(value.quality_observations).size !== value.quality_observations.length
    || !countsEqual(expected, value.expected_counts)) return false
  return value.upload_state === (countsEqual(expected, value.received_counts) ? 'verified' : 'mismatch')
}

export function createCollectionCoordinator({ load, save, identity, api, clock = Date.now, wait = ms => new Promise(r => setTimeout(r, ms)), onChange = () => {}, onDeleted = () => {} }) {
  let state = { version: 3, last_capture_sequence: 0, sessions: [], completed: [], deleted: [] }
  let inFlight = null, halted = false, storageBroken = false, unreadable = false, error = '', unsavedDeletion = null
  const paused = new Set(), retries = new Map()
  let wake = null
  const wakeRun = () => { if (wake) wake(); wake = null }
  const pending = (lane, sessions = state.sessions) => sessions.reduce((n, s) => n + s.outboxes[lane].length, 0)
  function scopedUploads() {
    const actor = identity(), latest = new Map()
    if (!actor.unlocked || !actor.clinicianId) return []
    // The phone clock can change between recordings, and an older upload can finish later.
    function consider(capture, source) {
      if (capture.clinicianId !== actor.clinicianId) return
      const previous = latest.get(capture.patient_id)
      if (!previous || capture.capture_sequence > previous.capture.capture_sequence) latest.set(capture.patient_id, { capture, source })
    }
    for (const capture of state.completed) consider(capture, 'completed')
    for (const capture of state.sessions) consider(capture, 'pending')
    for (const capture of state.deleted) consider(capture, 'deleted')
    return copy([...latest.values()].map(({ capture, source }) => {
      const { capture_id, clinicianId, patient_id, mobile_started_at, mobile_stopped_at } = capture
      if (source === 'deleted') {
        const local_discard_pending = unsavedDeletion === capture_id
        return { capture_id, clinicianId, patient_id, mobile_started_at, mobile_stopped_at, test_type: capture.test_type,
          completed: false, upload_state: 'deleted', expected_counts: capture.expected_counts, received_counts: null,
          discarded_counts: local_discard_pending ? null : capture.discarded_counts, local_discard_pending }
      }
      const completed = source === 'completed'
      const verification = completed ? capture.verification : null
      const test_type = completed ? capture.test_type : capture.totals === null ? null : capture.registration.test_type
      return { capture_id, clinicianId, patient_id, mobile_started_at, mobile_stopped_at, test_type, completed,
        upload_state: completed ? verification?.upload_state ?? 'unknown' : 'pending',
        expected_counts: completed ? verification?.expected_counts ?? null : capture.totals,
        received_counts: verification?.received_counts ?? null }
    }))
  }
  function snapshot() {
    const actor = identity()
    const sessions = actor.unlocked && actor.clinicianId ? state.sessions.filter(s => s.clinicianId === actor.clinicianId) : []
    const originalPending = pending('primary', sessions), radarPending = pending('radar', sessions)
    const pausedKeys = sessions.reduce((keys, s) => keys.concat(uploadKinds.map(kind => `${s.capture_id}:${kind}`).filter(key => paused.has(key))), [])
    return { pending: originalPending + radarPending, originalPending, radarPending, sessions: sessions.length, sending: !!inFlight,
      paused: halted || pausedKeys.length > 0, error, radarPaused: pausedKeys.some(k => k.endsWith(':radar')), primaryPaused: pausedKeys.some(k => k.endsWith(':primary')),
      deletionWritePending: !!unsavedDeletion && actor.unlocked && state.deleted.some(s => s.capture_id === unsavedDeletion && s.clinicianId === actor.clinicianId),
      uploads: scopedUploads() }
  }
  const publish = () => onChange(snapshot())
  function persist(next) {
    try { save(JSON.stringify(next)); state = next; storageBroken = false; unsavedDeletion = null }
    catch { storageBroken = true; halted = true; error = 'storage'; publish(); throw Error('storage') }
    publish()
  }
  function validate(restored) {
    if (![1, 2, 3].includes(restored?.version) || !Array.isArray(restored.sessions) || restored.sessions.length > 100) throw Error('storage')
    const captures = new Set()
    const sequences = new Set()
    function validateSequence(sequence) {
      if (!Number.isSafeInteger(sequence) || sequence < 1 || sequence > restored.last_capture_sequence || sequences.has(sequence)) throw Error('storage')
      sequences.add(sequence)
    }
    if (restored.version === 3 && (!Number.isSafeInteger(restored.last_capture_sequence) || restored.last_capture_sequence < 0)) throw Error('storage')
    for (const s of restored.sessions) {
      if (!s || typeof s.capture_id !== 'string' || !s.capture_id || captures.has(s.capture_id) || !s.clinicianId || !s.patient_id || !s.device_code || !timestamp(s.mobile_started_at) ||
        typeof s.created !== 'boolean' || !(s.mobile_stopped_at === null || timestamp(s.mobile_stopped_at))) throw Error('storage')
      captures.add(s.capture_id)
      const outboxes = restored.version === 1 ? { primary: s.events, radar: [] } : s.outboxes
      if (!outboxes || !lanes.every(l => Array.isArray(outboxes[l]))) throw Error('storage')
      const ids = new Set()
      const queued = emptyCounts()
      for (const lane of lanes) for (const e of outboxes[lane]) {
        if (!e || !e.event_id || ids.has(e.event_id) || laneOf(e.stream) !== lane || !timestamp(e.mobile_received_at)) throw Error('storage')
        ids.add(e.event_id)
        queued[e.stream] += 1
      }
      if (restored.version === 3) {
        validateSequence(s.capture_sequence)
        if (s.totals !== null && (!countsValid(s.totals) || !registrationBound(s.registration, s.patient_id)
          || streams.some(stream => s.totals[stream] < queued[stream]))) throw Error('storage')
      }
    }
    for (const lane of lanes) if (restored.sessions.reduce((n, s) => n + (restored.version === 1 ? lane === 'primary' ? s.events.length : 0 : s.outboxes[lane].length), 0) > 5000) throw Error('storage')
    if (restored.version === 3) {
      if (!Array.isArray(restored.completed) || restored.completed.length > completionLimit) throw Error('storage')
      for (const s of restored.completed) {
        if (!s || typeof s.capture_id !== 'string' || !s.capture_id || captures.has(s.capture_id) || !s.clinicianId || !s.patient_id || !timestamp(s.mobile_started_at)
          || !timestamp(s.mobile_stopped_at) || s.mobile_stopped_at < s.mobile_started_at
          || (s.verification === null ? s.test_type !== null : !knownType(s.test_type)
            || !validVerification(s.verification, s.capture_id, s.verification?.expected_counts))) throw Error('storage')
        validateSequence(s.capture_sequence)
        captures.add(s.capture_id)
      }
      if (restored.deleted !== undefined && !Array.isArray(restored.deleted)) throw Error('storage')
      for (const s of restored.deleted ?? []) {
        if (!s || typeof s.capture_id !== 'string' || !s.capture_id || captures.has(s.capture_id) || !s.clinicianId || !s.patient_id
          || !timestamp(s.mobile_started_at) || !timestamp(s.mobile_stopped_at) || s.mobile_stopped_at < s.mobile_started_at
          || !countsValid(s.discarded_counts) || (s.expected_counts === null ? s.test_type !== null : !knownType(s.test_type)
            || !countsValid(s.expected_counts) || streams.some(stream => s.expected_counts[stream] < s.discarded_counts[stream]))) throw Error('storage')
        validateSequence(s.capture_sequence)
        captures.add(s.capture_id)
      }
    }
  }
  try {
    const saved = load()
    if (saved) {
      const restored = JSON.parse(saved); validate(restored)
      let next = copy(restored), changed = restored.version < 3
      if (changed) {
        next = { version: 3, last_capture_sequence: next.sessions.length, completed: [],
          sessions: next.sessions.map(({ events, ...s }, index) => ({ ...s, totals: null, capture_sequence: index + 1,
          outboxes: restored.version === 1 ? { primary: events, radar: [] } : s.outboxes })) }
      }
      if (!next.deleted) next.deleted = []
      for (const s of next.sessions) if (!s.mobile_stopped_at) {
        const stamps = [s.mobile_started_at, s.last_received_at]
        for (const lane of lanes) for (const event of s.outboxes[lane]) stamps.push(event.mobile_received_at)
        s.mobile_stopped_at = latestTimestamp(stamps)
        changed = true
      }
      if (changed) {
        try { persist(next) }
        catch {
          // On a failed write keep legacy bytes on disk. A readable v2/v3
          // recovery may retry saving before it makes any network request.
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
  function markDeleted(id) {
    // Include events enqueued during the request as well as the rejected batch.
    const session = find(id)
    const { capture_id, clinicianId, patient_id, mobile_started_at, capture_sequence } = session
    const discarded_counts = emptyCounts()
    for (const lane of lanes) for (const event of session.outboxes[lane]) discarded_counts[event.stream] += 1
    const receipt = { capture_id, clinicianId, patient_id, mobile_started_at, capture_sequence, discarded_counts,
      mobile_stopped_at: session.mobile_stopped_at ?? latestTimestamp([mobile_started_at, session.last_received_at, new Date(clock()).toISOString()]),
      test_type: session.totals === null ? null : session.registration.test_type, expected_counts: session.totals }
    const next = { ...state, sessions: state.sessions.filter(s => s.capture_id !== id), deleted: [...state.deleted, receipt] }
    for (const kind of uploadKinds) {
      retries.delete(`${id}:${kind}`)
      paused.delete(`${id}:${kind}`)
    }
    if (error === 'upload' && !paused.size) error = ''
    try { persist(next) }
    catch (cause) {
      // Keep the old bytes on disk until a successful retry writes the terminal receipt.
      state = next
      unsavedDeletion = id
      throw cause
    } finally { onDeleted({ capture_id, clinicianId, patient_id }) }
  }
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
        const body = { capture_id, patient_id, device_code, mobile_started_at }
        if (session.totals !== null) Object.assign(body, { schema_version: 2, registration: copy(session.registration) })
        const result = await send(() => api.create(body, binding), session, binding)
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
        const body = { mobile_stopped_at: session.mobile_stopped_at }
        const known = session.totals !== null
        if (known) Object.assign(body, { schema_version: 2, final_counts: copy(session.totals) })
        const result = await send(() => api.stop(id, body, binding), session, binding)
        if (result?.capture_id !== id || !exact(result, known ? ['capture_id', 'verification'] : ['capture_id'])
          || (known && !validVerification(result.verification, id, session.totals))) throw receiptError()
        update(id, (s, next) => {
          const { capture_id, clinicianId, patient_id, mobile_started_at, mobile_stopped_at, capture_sequence } = s
          next.completed.push({ capture_id, clinicianId, patient_id, mobile_started_at, mobile_stopped_at, capture_sequence,
            test_type: known ? s.registration.test_type : null, verification: known ? copy(result.verification) : null })
          next.completed.sort((a, b) => b.capture_sequence - a.capture_sequence)
          next.completed.length = Math.min(next.completed.length, completionLimit)
          next.sessions = next.sessions.filter(s => s.capture_id !== id)
        })
        retries.delete(key); return true
      }
      return false
    } catch (cause) {
      if (statusOf(cause) === 410) { markDeleted(id); return true }
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
    if (!binding.unlocked || !binding.clinicianId) return
    // A bounded batch per lane/capture/round: old streams first; radar cannot starve.
    while (!halted) {
      assertCollectionIdentity({ collectionIdentity: binding }, identity())
      let progress = false; const ids = state.sessions.filter(s => s.clinicianId === binding.clinicianId).map(s => s.capture_id)
      for (const lane of lanes) for (const id of ids) { if (halted) return; if (await step(id, lane, binding)) progress = true }
      if (progress) continue
      const pendingRetries = ids.reduce((items, id) => items.concat(uploadKinds.map(kind => retries.get(`${id}:${kind}`)).filter(Boolean)), [])
      const waiting = pendingRetries.filter(r => !r.ready)
      if (pendingRetries.some(r => r.ready)) continue
      if (!waiting.length) break
      // A failed radar lane sleeps independently; enqueue wakes priority work now.
      const arrival = new Promise(resolve => { wake = resolve })
      await Promise.race([arrival, ...waiting.map(r => r.done)]); wake = null
    }
  }
  return {
    snapshot,
    laneFull(stream) { return pending(laneOf(stream)) >= 5000 },
    add(context) {
      if (storageBroken || unreadable) throw Error('storage')
      if (state.sessions.length >= 100 || pending('primary') >= 5000 || state.last_capture_sequence >= Number.MAX_SAFE_INTEGER) throw Error('capacity')
      if (find(context.capture_id) || state.completed.some(s => s.capture_id === context.capture_id)
        || state.deleted.some(s => s.capture_id === context.capture_id)) throw Error('capture_exists')
      const { capture_id, clinicianId, patient_id, device_code, mobile_started_at, registration } = context
      if (!registrationBound(registration, patient_id)) throw Error('registration_unsaved')
      const next = copy(state)
      next.last_capture_sequence += 1
      next.sessions.push({ capture_id, clinicianId, patient_id, device_code, mobile_started_at, registration: copy(registration),
        capture_sequence: next.last_capture_sequence,
        created: false, mobile_stopped_at: null, last_received_at: mobile_started_at,
        outboxes: { primary: [], radar: [] }, totals: emptyCounts() })
      persist(next)
      wakeRun()
    },
    enqueue(captureId, event) {
      if (storageBroken || unreadable) throw Error('storage')
      const lane = laneOf(event.stream); if (!lane) throw Error('stream')
      if (pending(lane) >= 5000) throw Error('capacity')
      const s = find(captureId); if (!s || s.mobile_stopped_at || s.totals === null) throw Error('closed')
      if (s.totals[event.stream] >= Number.MAX_SAFE_INTEGER) throw Error('capacity')
      update(captureId, session => {
        const box = createTelemetryOutbox({ events: session.outboxes[lane] })
        box.enqueue(event)
        session.outboxes[lane] = box.snapshot()
        session.totals[event.stream] += 1
        session.last_received_at = latestTimestamp([session.last_received_at, event.mobile_received_at])
      })
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
