import { it, expect } from 'vitest'
import { createCollectionCoordinator } from '../utils/collectionCoordinator'
import { createCollectionSession } from '../utils/collectionSession'

const started = '2026-11-02T12:00:00.000Z'
const received = '2026-11-02T12:00:00.010Z'
const context = { capture_id: 'capture-runtime', clinicianId: 11, patient_id: 7,
  device_code: 'IN-3', mobile_started_at: started }
const event = { event_id: 'event-runtime', stream: 'insole', stream_sequence: 0,
  connection_epoch: 1, mobile_received_at: received, payload: {} }

function queueFixture(restored) {
  let disk = restored
  const identity = () => ({ clinicianId: 11, authEpoch: 1, unlocked: true })
  const queue = createCollectionCoordinator({ load: () => disk, save: value => { disk = value },
    identity, api: {}, onChange: () => {} })
  return { queue, identity, disk: () => disk }
}

function withAppArrayMethods(operation) {
  const descriptors = ['at', 'flatMap'].map(name => [name, Object.getOwnPropertyDescriptor(Array.prototype, name)])
  try {
    for (const [name] of descriptors) Object.defineProperty(Array.prototype, name, { value: undefined, configurable: true, writable: true })
    return operation()
  } finally {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(Array.prototype, name, descriptor)
      else delete Array.prototype[name]
    }
  }
}

it.each(['insole', 'gps', 'radar'])('records %s without recent Array methods instead of reporting broken storage', stream => {
  const f = queueFixture()
  let serial = 0
  const session = createCollectionSession({ queue: f.queue, identity: f.identity,
    uuid: () => serial++ ? 'event-runtime' : 'capture-runtime', now: () => Date.parse(started) })
  withAppArrayMethods(() => {
    session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    session.receive('IN-3', 1, { stream, payload: {} }, Date.parse(received), 'capture-runtime')
  })
  expect(session.active?.capture_id).toBe('capture-runtime')
  expect(session.reason).toBe('')
  expect(session.radarReason).toBe('')
  expect(f.queue.snapshot()).toMatchObject({ pending: 1, error: '' })
  const saved = JSON.parse(f.disk()).sessions[0]
  expect(saved.last_received_at).toBe(received)
  expect(saved.outboxes[stream === 'radar' ? 'radar' : 'primary'][0]).toMatchObject({ event_id: 'event-runtime', stream })
})

it.each([1, 2])('restores open v%s records without losing queued events when Array methods are absent', version => {
  const session = { ...context, created: true, mobile_stopped_at: null, last_received_at: started,
    ...(version === 1 ? { events: [event] } : { outboxes: { primary: [event], radar: [] } }) }
  const f = withAppArrayMethods(() => queueFixture(JSON.stringify({ version, sessions: [session] })))
  expect(f.queue.snapshot()).toMatchObject({ sessions: 1, pending: 1, error: '', paused: false })
  const saved = JSON.parse(f.disk())
  expect(saved.version).toBe(2)
  expect(saved.sessions[0].mobile_stopped_at).toBe(received)
  expect(saved.sessions[0].outboxes.primary).toEqual([event])
})

it('stops at the latest durable event without Array.at or Array.flatMap', () => {
  const f = queueFixture()
  f.queue.add(context)
  f.queue.enqueue(context.capture_id, event)
  withAppArrayMethods(() => f.queue.stop(context.capture_id, started))
  const saved = JSON.parse(f.disk()).sessions[0]
  expect(saved.mobile_stopped_at).toBe(received)
  expect(saved.outboxes.primary).toEqual([event])
})
