export function createUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  // HBuilderX Android JS engines need the native UUID provider.
  if (typeof plus !== 'undefined' && plus.android) return String(plus.android.importClass('java.util.UUID').randomUUID())
  throw new Error('uuid_unavailable')
}

export function assertCollectionIdentity(custom, actor) {
  const required = custom?.collectionIdentity
  if (required && (!actor.unlocked || actor.clinicianId !== required.clinicianId || actor.authEpoch !== required.authEpoch)) {
    const error = new Error('collection_identity_changed')
    error.statusCode = 403
    throw error
  }
}

export function createCollectionSession({ queue, identity, uuid = createUuid, now = Date.now, onChange = () => {} }) {
  let active = null, reason = '', lastTime = null, sequences = { insole: 0, gps: 0 }
  const publish = () => onChange({ active: active ? { ...active } : null, reason })
  function stop(why = 'user', at = now()) {
    if (!active) return
    const current = active
    active = null
    reason = why
    const stopped = Number.isFinite(at) ? Math.max(at, lastTime) : lastTime
    try { queue.stop(current.capture_id, new Date(stopped).toISOString()) }
    catch { reason = 'storage' }
    publish()
  }
  return {
    get active() { return active },
    get reason() { return reason },
    start({ patientId, deviceCode, connected }) {
      const actor = identity()
      if (active || !connected || !actor.unlocked || !actor.clinicianId || !patientId || !deviceCode) throw new Error('capture_unavailable')
      const stamp = now()
      const context = { capture_id: uuid(), clinicianId: actor.clinicianId, authEpoch: actor.authEpoch,
        patient_id: patientId, device_code: deviceCode, mobile_started_at: new Date(stamp).toISOString() }
      queue.add(context)
      active = context; lastTime = stamp; sequences = { insole: 0, gps: 0 }; reason = ''
      publish()
      return context.capture_id
    },
    receive(deviceCode, epoch, parsed, receivedAt) {
      if (!active || active.device_code !== deviceCode) return
      try { assertCollectionIdentity({ collectionIdentity: active }, identity()) }
      catch { stop('identity', lastTime); return }
      if (!Number.isFinite(receivedAt) || receivedAt < lastTime) { stop('clock_rollback', lastTime); return }
      const event = { event_id: uuid(), stream: parsed.stream, stream_sequence: sequences[parsed.stream],
        connection_epoch: epoch, mobile_received_at: new Date(receivedAt).toISOString(), payload: parsed.payload }
      try { queue.enqueue(active.capture_id, event) }
      catch (error) { stop(error.message === 'capacity' ? 'capacity' : 'storage', lastTime); return }
      sequences[parsed.stream] += 1
      lastTime = receivedAt
      if (queue.snapshot().pending >= 5000) stop('capacity', lastTime)
    },
    stop(why = 'user') {
      const stamp = now()
      stop(stamp < lastTime ? 'clock_rollback' : why, stamp < lastTime ? lastTime : stamp)
    },
  }
}
