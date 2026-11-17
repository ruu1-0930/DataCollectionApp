import { describe, expect, it, vi } from 'vitest'
import { createCollectionCoordinator } from '../utils/collectionCoordinator'
import { savedRegistration } from './helpers/savedRegistration'

const stamp = '2026-10-23T00:00:00.000Z'
const stoppedAt = '2026-10-23T00:00:01.000Z'
const zero = { insole: 0, gps: 0, radar: 0 }
const context = (capture_id, patient_id = 7) => ({ capture_id, clinicianId: 11, patient_id,
  device_code: 'IN-3', mobile_started_at: stamp, registration: savedRegistration(patient_id) })
const sample = (id, stream, payload = {}) => ({ event_id: id, stream, stream_sequence: 0, connection_epoch: 1,
  mobile_received_at: stamp, payload })

function finalReceipt(id, expected, received = expected, state = 'verified') {
  return { capture_id: id, verification: { record_id: id, record_version: 'a'.repeat(64), observed_at: stoppedAt,
    expected_counts: expected, received_counts: received, upload_state: state, quality_observations: [] } }
}

function fixture(restored) {
  let disk = restored, failSave = false, actor = { clinicianId: 11, authEpoch: 1, unlocked: true }
  const api = {
    create: vi.fn(async body => ({ capture_id: body.capture_id })),
    batch: vi.fn(async (id, { events }) => ({ capture_id: id, results: events.map(e => ({
      event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: stamp,
    })) })),
    stop: vi.fn(async (id, body) => body.schema_version === 2 ? finalReceipt(id, body.final_counts) : { capture_id: id }),
  }
  const queue = createCollectionCoordinator({ load: () => disk, save: value => {
    if (failSave) throw Error('disk')
    disk = value
  }, identity: () => actor, api, wait: async () => {} })
  return { queue, api, disk: () => disk, failSave: () => { failSave = true }, actor: value => { actor = value } }
}

describe('durable V3 collection finalization', () => {
  it('test_final_counts_include_events_already_acked', async () => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.enqueue('capture', sample('insole-1', 'insole'))
    f.queue.enqueue('capture', sample('gps-1', 'gps', { raw_line: 'GPS1,1,0,nan,nan,nan,nan,0,nan,0,,13,0' }))
    await f.queue.drain()
    expect(JSON.parse(f.disk()).sessions[0].outboxes.primary).toEqual([])
    f.queue.enqueue('capture', sample('radar-1', 'radar'))
    f.queue.stop('capture', stoppedAt)
    await f.queue.drain()
    expect(f.api.stop.mock.calls[0][1]).toEqual({ mobile_stopped_at: stoppedAt, schema_version: 2,
      final_counts: { insole: 1, gps: 1, radar: 1 } })
    expect(f.api.create.mock.calls[0][0]).toEqual({ capture_id: 'capture', patient_id: 7, device_code: 'IN-3',
      mobile_started_at: stamp, schema_version: 2, registration: savedRegistration(7) })
    expect(f.queue.snapshot().uploads[0]).toMatchObject({ upload_state: 'verified',
      received_counts: { insole: 1, gps: 1, radar: 1 } })
  })

  it('restarts after a lost stop receipt and sends the same declaration with optional stream zero', async () => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.enqueue('capture', sample('first', 'insole'))
    f.queue.stop('capture', stoppedAt)
    f.api.stop.mockRejectedValue({ errMsg: 'request:fail timeout' })
    await f.queue.drain()
    expect(f.api.stop).toHaveBeenCalledTimes(4)
    expect(f.queue.snapshot()).toMatchObject({ pending: 0, sessions: 1, uploads: [{ upload_state: 'pending' }] })
    const recovered = fixture(f.disk())
    const counts = { insole: 1, gps: 0, radar: 0 }
    await recovered.queue.drain()
    expect(recovered.api.create).not.toHaveBeenCalled()
    expect(recovered.api.batch).not.toHaveBeenCalled()
    expect(recovered.api.stop.mock.calls[0][1]).toEqual(f.api.stop.mock.calls[0][1])
    expect(recovered.api.stop.mock.calls[0][1].final_counts).toEqual(counts)
    expect(recovered.queue.snapshot()).toMatchObject({ sessions: 0, uploads: [{ upload_state: 'verified', received_counts: counts }] })
  })

  it('keeps a mismatch and the compared counts through restart', async () => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.stop('capture', stoppedAt)
    f.api.stop.mockResolvedValue(finalReceipt('capture', zero, { ...zero, gps: 1 }, 'mismatch'))
    await f.queue.drain()
    const restarted = fixture(f.disk())
    expect(restarted.queue.snapshot()).toMatchObject({ sessions: 0, pending: 0, uploads: [{
      expected_counts: zero, received_counts: { insole: 0, gps: 1, radar: 0 }, upload_state: 'mismatch',
    }] })
    restarted.actor({ clinicianId: 12, authEpoch: 2, unlocked: true })
    expect(restarted.queue.snapshot().uploads).toEqual([])
    restarted.actor({ clinicianId: 11, authEpoch: 3, unlocked: false })
    expect(restarted.queue.snapshot().uploads).toEqual([])
  })

  it.each([
    { capture_id: 'capture' },
    finalReceipt('capture', zero, { ...zero, radar: 1 }),
    finalReceipt('capture', { ...zero, gps: 1 }),
    { ...finalReceipt('other', zero), capture_id: 'capture' },
  ])('retains a V3 session when a stop response cannot confirm its own counts', async response => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.stop('capture', stoppedAt)
    f.api.stop.mockResolvedValue(response)
    await f.queue.drain()
    expect(f.queue.snapshot()).toMatchObject({ pending: 0, sessions: 1, paused: true, uploads: [{ upload_state: 'pending' }] })
  })

  it.each([
    ['impossible calendar date', { observed_at: '2026-02-31T10:00:00.000Z' }],
    ['unknown quality observation', { quality_observations: ['invented_code'] }],
    ['duplicate quality observation', { quality_observations: ['no_insole_frames', 'no_insole_frames'] }],
  ])('rejects a structurally invalid stop receipt with %s and preserves the declaration', async (_, changes) => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.stop('capture', stoppedAt)
    const response = finalReceipt('capture', zero)
    f.api.stop.mockResolvedValueOnce({ ...response, verification: { ...response.verification, ...changes } })
    await f.queue.drain()
    expect(f.queue.snapshot()).toMatchObject({ sessions: 1, paused: true, uploads: [{ upload_state: 'pending' }] })
    expect(JSON.parse(f.disk()).completed).toEqual([])
    expect(JSON.parse(f.disk()).sessions[0]).toMatchObject({ capture_id: 'capture', totals: zero, mobile_stopped_at: stoppedAt })
    await f.queue.drain(true)
    expect(f.api.stop.mock.calls[1][1]).toEqual(f.api.stop.mock.calls[0][1])
    expect(f.queue.snapshot()).toMatchObject({ sessions: 0, uploads: [{ upload_state: 'verified' }] })
  })

  it('keeps the newly started capture through phone clock rollback, completion and restart', async () => {
    const f = fixture()
    f.queue.add({ ...context('old'), mobile_started_at: '2026-10-23T10:00:00.000Z' })
    f.queue.stop('old', '2026-10-23T10:00:01.000Z')
    await f.queue.drain()
    f.queue.add({ ...context('new'), mobile_started_at: '2026-10-23T09:00:00.000Z' })
    expect(f.queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'pending' })
    f.queue.stop('new', '2026-10-23T09:00:01.000Z')
    await f.queue.drain()
    expect(f.queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'verified' })
    expect(fixture(f.disk()).queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'verified' })
  })

  it('keeps the latest capture when an earlier capture completes late after restart', async () => {
    const f = fixture()
    f.queue.add(context('old'))
    f.queue.stop('old', stoppedAt)
    f.api.stop.mockRejectedValueOnce({ statusCode: 422 })
    await f.queue.drain()
    f.queue.add(context('new'))
    f.queue.stop('new', stoppedAt)
    await f.queue.drain()
    expect(f.queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'verified' })
    const restarted = fixture(f.disk())
    expect(restarted.queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'verified' })
    await restarted.queue.drain()
    expect(restarted.api.stop.mock.calls[0][0]).toBe('old')
    expect(restarted.queue.snapshot().uploads[0]).toMatchObject({ capture_id: 'new', upload_state: 'verified' })
    expect(JSON.parse(restarted.disk()).completed).toHaveLength(2)
  })

  it('projects the frozen test type and capture times before and after a durable stop receipt', async () => {
    const f = fixture()
    const opened = context('tug')
    opened.registration = { ...opened.registration, test_type: 'tug' }
    f.queue.add(opened)
    opened.registration.test_type = 'static_standing'
    f.queue.stop('tug', stoppedAt)
    const expected = { capture_id: 'tug', test_type: 'tug', mobile_started_at: stamp, mobile_stopped_at: stoppedAt }
    expect(f.queue.snapshot().uploads[0]).toMatchObject({ ...expected, upload_state: 'pending' })
    await f.queue.drain()
    expect(JSON.parse(f.disk()).completed[0]).toMatchObject(expected)
    expect(fixture(f.disk()).queue.snapshot().uploads[0]).toMatchObject({ ...expected, upload_state: 'verified' })
  })

  it.each([1, 2])('migrates V%s with the original queue bytes and unknown historical totals', async version => {
    const original = sample('gps-event', 'gps', { raw_line: 'GPS1,12,0,nan,nan,nan,nan,0,nan,0,,39,0' })
    const old = { ...context('legacy'), created: false, mobile_stopped_at: null,
      ...(version === 1 ? { events: [original] } : { outboxes: { primary: [original], radar: [] } }) }
    const f = fixture(JSON.stringify({ version, sessions: [old] }))
    const migrated = JSON.parse(f.disk())
    expect(migrated.version).toBe(3)
    expect(migrated.sessions[0]).toMatchObject({ totals: null, registration: old.registration,
      outboxes: { primary: [original], radar: [] } })
    await f.queue.drain()
    expect(f.api.create.mock.calls[0][0]).toEqual({ capture_id: 'legacy', patient_id: 7, device_code: 'IN-3', mobile_started_at: stamp })
    expect(f.api.batch.mock.calls[0][1]).toEqual({ events: [original] })
    expect(f.api.stop.mock.calls[0][1]).toEqual({ mobile_stopped_at: stamp })
    expect(f.queue.snapshot().uploads).toEqual([expect.objectContaining({ capture_id: 'legacy', patient_id: 7,
      test_type: null, mobile_started_at: stamp, mobile_stopped_at: stamp,
      expected_counts: null, received_counts: null, upload_state: 'unknown' })])
  })

  it('leaves counts and original events intact if a new enqueue cannot be persisted', () => {
    const f = fixture()
    f.queue.add(context('capture'))
    f.queue.enqueue('capture', sample('queued', 'gps'))
    f.failSave()
    expect(() => f.queue.enqueue('capture', sample('unsaved', 'radar'))).toThrow('storage')
    const saved = JSON.parse(f.disk()).sessions[0]
    expect(saved.totals).toEqual({ insole: 0, gps: 1, radar: 0 })
    expect(saved.outboxes).toEqual({ primary: [sample('queued', 'gps')], radar: [] })
  })

  it('keeps recent receipts bounded and a newer pending result ahead of a successful one', async () => {
    const f = fixture()
    for (let i = 0; i < 22; i++) {
      const id = `capture-${i}`
      f.queue.add(context(id, 7 + i % 2))
      f.queue.stop(id, stoppedAt)
    }
    await f.queue.drain()
    expect(JSON.parse(f.disk()).completed).toHaveLength(20)
    expect(f.api.stop.mock.calls[0][1].final_counts).toEqual(zero)
    expect(f.queue.snapshot().uploads.find(r => r.patient_id === 7).capture_id).toBe('capture-20')
    f.queue.add({ ...context('new'), mobile_started_at: stoppedAt })
    expect(f.queue.snapshot().uploads.find(r => r.patient_id === 7)).toMatchObject({ capture_id: 'new', upload_state: 'pending' })
    expect(f.queue.snapshot().uploads.find(r => r.patient_id === 8)).toMatchObject({ capture_id: 'capture-21', upload_state: 'verified' })
  })
})
