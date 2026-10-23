import { it, expect, vi } from 'vitest'
import { createCollectionCoordinator } from '../utils/collectionCoordinator'
import { createCollectionSession } from '../utils/collectionSession'
const stamp = '2026-10-23T00:00:00.000Z'
const context = capture_id => ({ capture_id, clinicianId: 11, patient_id: 7, device_code: 'IN-3', mobile_started_at: stamp })
let serial = 0
const event = (stream, at = stamp) => ({ event_id: `event-${++serial}`, stream, stream_sequence: serial, connection_epoch: 1, mobile_received_at: at, payload: {} })
export function fixture({ restored, failSave = false, failRadar = false } = {}) {
  let disk = restored, actor = { clinicianId: 11, authEpoch: 1, unlocked: true }, fail = failSave
  const sent = []
  const api = {
    create: async body => { sent.push(['create', body.capture_id]); return { capture_id: body.capture_id } },
    batch: async (id, body) => { sent.push(['batch', id, body]); if (failRadar && body.events[0].stream === 'radar') throw { statusCode: 503 }; return { capture_id: id, results: body.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: stamp })) } },
    stop: async (id, body) => { sent.push(['stop', id, body]); return { capture_id: id } },
  }
  const options = { load: () => disk, save: value => { if (fail) throw Error('disk'); disk = value }, identity: () => actor, api, wait: async () => {} }
  const queue = createCollectionCoordinator(options)
  return { queue, api, sent, options, disk: () => disk, fail: value => { fail = value }, actor: value => { actor = value } }
}
it('test_two_outboxes_stop_once_after_all_receipts', async () => {
  const f = fixture(); f.queue.add(context('one'))
  f.queue.enqueue('one', event('insole')); f.queue.enqueue('one', event('gps')); f.queue.enqueue('one', event('radar')); f.queue.stop('one', stamp)
  await f.queue.drain(); await f.queue.drain()
  expect(f.sent.map(r => r[0])).toEqual(['create', 'batch', 'batch', 'batch', 'stop'])
  expect(f.sent.filter(r => r[0] === 'batch').every(r => new Set(r[2].events.map(e => e.stream)).size === 1)).toBe(true)
  expect(f.queue.snapshot().sessions).toBe(0)
})
it('test_radar_failure_does_not_block_insole', async () => {
  const f = fixture({ failRadar: true }); f.queue.add(context('old')); f.queue.enqueue('old', event('radar')); f.queue.stop('old', stamp)
  f.queue.add(context('new')); f.queue.enqueue('new', event('insole')); f.queue.stop('new', stamp)
  await f.queue.drain()
  expect(f.sent.filter(r => r[0] === 'batch' && r[1] === 'new')).toHaveLength(1)
  expect(f.sent.filter(r => r[0] === 'stop').map(r => r[1])).toEqual(['new'])
  expect(f.queue.snapshot()).toMatchObject({ originalPending: 0, radarPending: 1, radarPaused: true })
})
it('test_radar_capacity_pauses_only_radar', () => {
  const full = { ...context('old'), created: true, mobile_stopped_at: stamp, outboxes: { primary: [], radar: Array.from({ length: 5000 }, () => event('radar')) } }
  const f = fixture({ restored: JSON.stringify({ version: 2, sessions: [full] }) })
  const session = createCollectionSession({ queue: f.queue, identity: f.options.identity, uuid: () => 'new', now: () => Date.parse(stamp) })
  session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
  session.receiveRadar('new', 5, {}, Date.parse(stamp))
  session.receive('IN-3', 1, { stream: 'insole', payload: {} }, Date.parse(stamp))
  expect(session.active.capture_id).toBe('new'); expect(session.radarReason).toBe('capacity')
  expect(f.queue.snapshot()).toMatchObject({ originalPending: 1, radarPending: 5000 })
})
it('test_restore_stop_covers_latest_durable_radar', async () => {
  const f = fixture(); f.queue.add(context('one')); f.queue.enqueue('one', event('radar', '2026-10-23T00:00:05.000Z'))
  const recovered = fixture({ restored: f.disk() }); await recovered.queue.drain()
  expect(recovered.sent.at(-1)).toEqual(['stop', 'one', { mobile_stopped_at: '2026-10-23T00:00:05.000Z' }])
})
it('test_legacy_queue_migration_preserves_ids', async () => {
  const original = event('gps')
  const old = JSON.stringify({ version: 1, sessions: [{ ...context('legacy'), created: true, mobile_stopped_at: stamp, last_received_at: stamp, events: [original] }] })
  const f = fixture({ restored: old })
  const migrated = JSON.parse(f.disk())
  expect(migrated.version).toBe(2); expect(migrated.sessions[0]).toMatchObject({ created: true, mobile_stopped_at: stamp, outboxes: { primary: [original], radar: [] } })
  await f.queue.drain()
  expect(f.sent.map(r => r[0])).toEqual(['batch', 'stop']); expect(f.sent[0][2].events[0]).toEqual(original)
})
it('test_migration_failure_preserves_old_bytes', async () => {
  const old = JSON.stringify({ version: 1, sessions: [{ ...context('legacy'), created: true, events: [event('gps')], mobile_stopped_at: stamp }] })
  const f = fixture({ restored: old, failSave: true }); f.fail(false); await f.queue.drain(true)
  expect(f.disk()).toBe(old); expect(f.sent).toEqual([]); expect(f.queue.snapshot().error).toBe('storage')
})
it('test_old_callback_cannot_enter_new_capture', () => {
  const f = fixture(); let id = 0
  const session = createCollectionSession({ queue: f.queue, identity: f.options.identity, uuid: () => `capture-${++id}`, now: () => Date.parse(stamp) })
  const old = session.start({ patientId: 7, deviceCode: 'IN-3', connected: true }); session.stop()
  const current = session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
  session.receiveRadar(old, 1, {}, Date.parse(stamp)); session.receiveRadar(current, 1, {}, Date.parse(stamp))
  expect(f.queue.snapshot().radarPending).toBe(1)
  expect(JSON.parse(f.disk()).sessions[0].outboxes.radar).toEqual([])
})
it('serves newly arrived insole events during radar retry backoff', async () => {
  vi.useFakeTimers()
  try {
    const f = fixture({ failRadar: true })
    const queue = createCollectionCoordinator({ ...f.options, wait: ms => new Promise(resolve => setTimeout(resolve, ms)) })
    queue.add(context('one')); queue.enqueue('one', event('radar'))
    const draining = queue.drain(); await vi.advanceTimersByTimeAsync(0)
    queue.enqueue('one', event('insole')); await vi.advanceTimersByTimeAsync(0)
    expect(f.sent.some(r => r[0] === 'batch' && r[2].events[0].stream === 'insole')).toBe(true)
    await vi.advanceTimersByTimeAsync(7000); await draining
    expect(f.sent.filter(r => r[0] === 'batch' && r[2].events[0].stream === 'radar')).toHaveLength(4)
  } finally { vi.useRealTimers() }
})
it('halts both outboxes on an unauthorized envelope', async () => {
  const f = fixture(); f.queue.add(context('one')); f.queue.enqueue('one', event('insole')); f.queue.enqueue('one', event('radar'))
  f.api.batch = async () => { throw { data: { code: 401 } } }
  await f.queue.drain()
  expect(f.queue.snapshot()).toMatchObject({ error: 'identity', paused: true, originalPending: 1, radarPending: 1 })
})
it('gives radar a bounded turn while original events keep arriving', async () => {
  const f = fixture(); f.queue.add(context('one')); f.queue.enqueue('one', event('insole')); f.queue.enqueue('one', event('radar'))
  const realBatch = f.api.batch; let originals = 0
  f.api.batch = async (id, body) => {
    if (body.events[0].stream === 'insole' && ++originals < 4) f.queue.enqueue(id, event('insole'))
    return realBatch(id, body)
  }
  await f.queue.drain()
  const order = f.sent.filter(r => r[0] === 'batch').map(r => r[2].events[0].stream)
  expect(order.indexOf('radar')).toBeLessThan(3); expect(originals).toBe(4)
})
it('test_readable_v2_restore_stop_write_failure_allows_manual_retry_before_send', async () => {
  const durable = JSON.stringify({ version: 2, sessions: [{ ...context('recover'), created: true, mobile_stopped_at: null, last_received_at: stamp,
    outboxes: { primary: [], radar: [event('radar', '2026-10-23T00:00:05.000Z')] } }] })
  const f = fixture({ restored: durable, failSave: true })
  expect(f.disk()).toBe(durable); expect(f.queue.snapshot().error).toBe('storage')
  await f.queue.drain(); expect(f.sent).toEqual([])
  f.fail(false)
  const batch = f.api.batch
  f.api.batch = async (id, body) => {
    expect(JSON.parse(f.disk()).sessions[0].mobile_stopped_at).toBe('2026-10-23T00:00:05.000Z')
    return batch(id, body)
  }
  await f.queue.drain(true)
  expect(f.sent.map(r => r[0])).toEqual(['batch', 'stop'])
  expect(f.sent.at(-1)).toEqual(['stop', 'recover', { mobile_stopped_at: '2026-10-23T00:00:05.000Z' }])
  expect(f.queue.snapshot()).toMatchObject({ pending: 0, sessions: 0, paused: false, error: '' })
})
