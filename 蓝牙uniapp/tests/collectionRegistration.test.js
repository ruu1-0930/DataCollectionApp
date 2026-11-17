import { describe, it, expect, vi } from 'vitest'
import { createCollectionSession } from '../utils/collectionSession'
import { createRegistrationDraft } from '../utils/collectionRegistration'

const profile = { name: '合成患者', phone: null, gender: '男', age: 60, height_cm: 170, weight_kg: 65, shoe_size_eu: 40.5 }
const form = { ...profile, test_type: 'walk_10m_usual', remarks: '' }

function setup(options = {}) {
  const disk = new Map()
  const actor = { actorId: 11, patientId: 7, authEpoch: 1, unlocked: true }
  const dependencies = { load: key => disk.get(key), save: (key, value) => disk.set(key, value),
    saveProfile: vi.fn(async value => value), identity: () => actor, ...options }
  const registration = createRegistrationDraft(dependencies)
  const queue = { add: vi.fn(), stop: vi.fn() }
  let serial = 0
  const uuid = vi.fn(() => `capture-${++serial}`)
  const session = createCollectionSession({ queue, uuid,
    identity: () => ({ clinicianId: actor.actorId, authEpoch: actor.authEpoch, unlocked: actor.unlocked }),
    registrationFor: (patientId, actorId) => registration.savedFor(patientId, actorId),
  })
  const start = saved => session.start({ patientId: actor.patientId, deviceCode: 'IN-3', connected: true, registration: saved })
  return { actor, disk, dependencies, registration, queue, session, start, uuid }
}

describe('pre-capture registration gate', () => {
  it('test_edit_after_save_blocks_start_until_saved_again', async () => {
    const { registration, queue, session, start, uuid } = setup()
    registration.edit(form)
    expect(() => start(null)).toThrow('registration_unsaved')
    const first = await registration.save()
    registration.edit({ test_type: 'tug', remarks: '第二次登记' })
    expect(() => start(first)).toThrow('registration_unsaved')
    const current = await registration.save()
    expect(() => start(first)).toThrow('registration_unsaved')
    expect(queue.add).not.toHaveBeenCalled()
    expect(uuid).not.toHaveBeenCalled()
    expect(start(current)).toBe('capture-1')
    expect(() => start(current)).toThrow('capture_unavailable')
    expect(queue.add).toHaveBeenCalledTimes(1)
    const frozen = queue.add.mock.calls[0][0].registration
    expect(frozen).toEqual({ schema_version: 1, patient_id: 7, patient_snapshot: {
      name: profile.name, gender: '男', age: 60, height_cm: 170, weight_kg: 65, shoe_size_eu: 40.5,
    }, test_type: 'tug', remarks: '第二次登记' })
    expect(frozen).not.toBe(current)
    expect(Object.isFrozen(frozen.patient_snapshot)).toBe(true)
    session.stop()
    expect(start(current)).toBe('capture-2')
  })

  it('keeps the input and requires both profile and local save to succeed', async () => {
    const saveProfile = vi.fn().mockRejectedValueOnce(Error('network')).mockImplementation(async value => value)
    const save = vi.fn()
    const { registration, queue, start } = setup({ saveProfile, save })
    registration.edit(form)
    await expect(registration.save()).rejects.toThrow('network')
    expect(registration.value).toEqual(form)
    save.mockImplementationOnce(() => { throw Error('storage') })
    await expect(registration.save()).rejects.toThrow('storage')
    expect(registration.value).toEqual(form)
    expect(registration.savedFor(7, 11)).toBeNull()
    expect(() => start(null)).toThrow('registration_unsaved')
    expect(queue.add).not.toHaveBeenCalled()
    await expect(registration.save()).resolves.toMatchObject({ test_type: 'walk_10m_usual' })
  })

  it('restores only the doctor and patient scoped draft and requires it to be saved again', async () => {
    const { actor, registration, dependencies, disk } = setup()
    registration.edit({ ...form, remarks: '甲的草稿' })
    const saved = await registration.save()
    const restored = createRegistrationDraft(dependencies)
    expect(restored.value.remarks).toBe('甲的草稿')
    expect(restored.savedFor(7, 11)).toBeNull()
    actor.patientId = 8
    expect(registration.value.name).toBe('')
    registration.edit({ ...form, remarks: '乙的草稿' })
    expect(registration.savedFor(7, 11)).toBeNull()
    actor.actorId = 12
    expect(registration.value.remarks).toBe('')
    actor.actorId = 11
    actor.patientId = 7
    expect(registration.value.remarks).toBe('甲的草稿')
    expect(registration.savedFor(7, 11)).toBeNull()
    expect(await registration.save()).toEqual(saved)
    expect([...disk.keys()]).toEqual(['collection_registration_draft_v1:11:7', 'collection_registration_draft_v1:11:8'])
  })

  it('allows the new patient to save while a previous patient’s save is still pending', async () => {
    let completePrevious
    const saveProfile = vi.fn().mockImplementationOnce(value => new Promise(resolve => { completePrevious = () => resolve(value) }))
      .mockImplementation(async value => value)
    const { actor, registration } = setup({ saveProfile })
    registration.edit(form)
    const previous = expect(registration.save()).rejects.toThrow('registration_changed')
    actor.patientId = 8
    registration.edit({ ...form, remarks: '乙的登记' })
    const current = expect(registration.save()).resolves.toMatchObject({ patient_id: 8, remarks: '乙的登记' })
    completePrevious()
    await Promise.all([previous, current])
    expect(registration.savedFor(8, 11)).toMatchObject({ patient_id: 8 })
    expect(saveProfile).toHaveBeenCalledTimes(2)
  })

  it('does not expose the persisted draft while the operator is locked', () => {
    const { actor, registration } = setup()
    registration.edit(form)
    actor.unlocked = false
    expect(registration.value.name).toBe('')
    expect(registration.savedFor(7, 11)).toBeNull()
  })
})
