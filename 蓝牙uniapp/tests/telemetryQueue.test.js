import { describe, expect, it, vi } from 'vitest'
import { createTelemetryQueue } from '../utils/telemetryQueue'
import { createCollectionSession, assertCollectionIdentity } from '../utils/collectionSession'

let id = 0
const uuid = () => `00000000-0000-4000-8000-${String(++id).padStart(12, '0')}`
const start = '2026-10-19T00:00:00.000Z'
const gps = { stream: 'gps', payload: { raw_line: 'GPS1,1,0,,,,,0,,0,,0,0' } }
function fixture({ fail, saveFailure = false, restored } = {}) {
  let disk = restored, actor = { clinicianId: 11, authEpoch: 1, unlocked: true }, now = Date.parse(start), savingFails = saveFailure
  const requests = []
  const api = {
    create: async (body, identity) => { requests.push(['create', body, identity]); if (fail) fail('create'); return { capture_id: body.capture_id } },
    batch: async (captureId, body, identity) => { requests.push(['batch', captureId, body, identity]); if (fail) fail('batch'); return { capture_id: captureId, results: body.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'accepted', server_received_at: start })) } },
    stop: async (captureId, body, identity) => { requests.push(['stop', captureId, body, identity]); if (fail) fail('stop'); return { capture_id: captureId } },
  }
  const queue = createTelemetryQueue({ load: () => disk, save: value => { if (savingFails) throw Error('disk'); disk = value },
    identity: () => actor, api, wait: async () => {} })
  const session = createCollectionSession({ queue, uuid, now: () => now, identity: () => actor })
  return { queue, session, api, requests, disk: () => disk, actor: value => { actor = value }, time: value => { now = value },
    savingFails: value => { savingFails = value } }
}

describe('fixed collection window and durable FIFO', () => {
  it('persists before send and drains create, matching stream batches, then stop', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    for (let i = 0; i < 51; i++) f.session.receive('IN-3', 4, gps, Date.parse(start) + i)
    f.session.receive('IN-3', 4, { stream: 'insole', payload: { left_speed: 1, right_speed: 2 } }, Date.parse(start) + 60)
    f.time(Date.parse(start) + 100)
    f.session.stop('user')
    expect(JSON.parse(f.disk()).sessions[0].events).toHaveLength(52)
    await f.queue.drain()
    expect(f.requests.map(r => r[0])).toEqual(['create', 'batch', 'batch', 'batch', 'stop'])
    expect(f.requests.filter(r => r[0] === 'batch').map(r => r[2].events.length)).toEqual([50, 1, 1])
    expect(f.requests[0][1]).toMatchObject({ patient_id: 7, device_code: 'IN-3', mobile_started_at: start })
    expect(f.requests[1][2].events[0]).toMatchObject({ stream_sequence: 0, connection_epoch: 4, mobile_received_at: start })
    expect(f.requests[3][2].events[0]).toMatchObject({ stream: 'insole', stream_sequence: 0 })
    expect(f.queue.snapshot().pending).toBe(0)
  })
  it('keeps identities after response loss, retries three times, then waits for manual retry', async () => {
    const f = fixture({ fail: () => { throw { statusCode: 503 } } })
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    await f.queue.drain()
    expect(f.requests).toHaveLength(4)
    expect(new Set(f.requests.map(r => r[1].capture_id)).size).toBe(1)
    expect(f.queue.snapshot().pending).toBe(1)
    await f.queue.drain()
    expect(f.requests).toHaveLength(4)
    f.api.create = async body => ({ capture_id: body.capture_id })
    let first
    f.api.batch = async (captureId, body) => {
      if (!first) { first = JSON.stringify(body); throw { errMsg: 'request:fail timeout' } }
      expect(JSON.stringify(body)).toBe(first)
      return { capture_id: captureId, results: body.events.map(e => ({ event_id: e.event_id, stream: e.stream, status: 'duplicate', server_received_at: start })) }
    }
    await f.queue.drain(true)
    expect(f.queue.snapshot().pending).toBe(0)
  })
  it.each([400, 401, 403, 409, 422])('retains pending on HTTP %i without automatic retry', async statusCode => {
    const f = fixture({ fail: () => { throw { statusCode } } })
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    await f.queue.drain()
    expect(f.requests).toHaveLength(1)
    expect(f.queue.snapshot().sessions).toBe(1)
  })
  it('never deletes events from unrelated or incomplete receipts', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 0, gps, Date.parse(start))
    f.api.batch = async captureId => ({ capture_id: captureId, results: [{ event_id: uuid(), stream: 'gps', status: 'accepted', server_received_at: start }] })
    await f.queue.drain()
    expect(f.queue.snapshot().pending).toBe(1)
  })
  it('restores pending after restart, closes at last persisted sample, and uses same event ID', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 2, gps, Date.parse(start) + 20)
    const oldId = JSON.parse(f.disk()).sessions[0].events[0].event_id
    const restored = fixture({ restored: f.disk() })
    expect(restored.session.active).toBe(null)
    await restored.queue.drain()
    expect(restored.requests[1][2].events[0].event_id).toBe(oldId)
    expect(restored.requests[2][2]).toEqual({ mobile_stopped_at: '2026-10-19T00:00:00.020Z' })
  })
  it('halts capture at last sample on clock rollback and prevents new events', () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start) + 20)
    f.session.receive('IN-3', 1, gps, Date.parse(start) - 1)
    const saved = JSON.parse(f.disk()).sessions[0]
    expect(saved.mobile_stopped_at).toBe('2026-10-19T00:00:00.020Z')
    expect(saved.events).toHaveLength(1)
    expect(f.session.active).toBe(null)
    expect(f.session.reason).toBe('clock_rollback')
  })
  it('stops and retains old identity when actor/auth epoch changes', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.actor({ clinicianId: 12, authEpoch: 2, unlocked: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    await f.queue.drain()
    expect(f.requests).toEqual([])
    expect(JSON.parse(f.disk()).sessions[0].clinicianId).toBe(11)
    expect(f.session.active).toBe(null)
    expect(() => assertCollectionIdentity({ collectionIdentity: { clinicianId: 11, authEpoch: 1 } }, { clinicianId: 12, authEpoch: 2, unlocked: true })).toThrow()
  })
  it('rechecks identity after an in-flight create before sending events', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    f.api.create = async body => { f.actor({ clinicianId: 12, authEpoch: 2, unlocked: true }); return { capture_id: body.capture_id } }
    await f.queue.drain()
    expect(f.requests).toEqual([])
    expect(f.queue.snapshot().pending).toBe(1)
  })
  it('refuses event 5001 without overwriting and stops capture', () => {
    const old = fixture()
    old.session.start({ patientId: 6, deviceCode: 'IN-3', connected: true })
    old.session.receive('IN-3', 1, gps, Date.parse(start))
    const document = JSON.parse(old.disk())
    document.sessions[0].mobile_stopped_at = start
    const sample = document.sessions[0].events[0]
    document.sessions[0].events = Array.from({ length: 4999 }, (_, stream_sequence) => ({ ...sample, event_id: uuid(), stream_sequence }))
    const f = fixture({ restored: JSON.stringify(document) })
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    expect(f.queue.snapshot().pending).toBe(5000)
    expect(f.session.active).toBe(null)
    expect(f.session.reason).toBe('capacity')
  })
  it.each(['not-json', '{"version":1,"sessions":[{}]}'])('never overwrites unreadable storage even on manual retry: %s', async restored => {
    const f = fixture({ restored })
    await f.queue.drain(true)
    expect(f.disk()).toBe(restored)
    expect(f.queue.snapshot().error).toBe('storage')
    expect(f.requests).toEqual([])
  })
  it('does not send overlapping requests when two drains race', async () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    const first = f.queue.drain()
    const second = f.queue.drain()
    expect(second).toBe(first)
    await first
    expect(f.requests.map(r => r[0])).toEqual(['create', 'batch'])
  })
  it('stops explicitly on storage failure and preserves the prior durable queue', () => {
    const f = fixture()
    f.session.start({ patientId: 7, deviceCode: 'IN-3', connected: true })
    f.savingFails(true)
    f.session.receive('IN-3', 1, gps, Date.parse(start))
    expect(f.session.active).toBe(null)
    expect(f.session.reason).toBe('storage')
    expect(JSON.parse(f.disk()).sessions[0].events).toHaveLength(0)
  })
})
