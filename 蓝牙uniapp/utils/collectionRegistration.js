import { normalizePatientProfile } from './patient'

export const COLLECTION_TEST_TYPES = [
  { code: 'static_standing', label: '静止站立测试' },
  { code: 'walk_10m_usual', label: '10m常速步行测试' },
  { code: 'five_times_sit_to_stand', label: '五次起立测试' },
  { code: 'tug', label: 'TUG综合测试' },
  { code: 'free_capture', label: '自由采集' },
]
const clone = value => JSON.parse(JSON.stringify(value))
const freeze = value => { Object.values(value).forEach(v => { if (v && typeof v === 'object') freeze(v) }); return Object.freeze(value) }
const empty = () => ({ name: '', phone: null, gender: '', age: null, height_cm: null, weight_kg: null, shoe_size_eu: null, test_type: '', remarks: '' })
const binding = actor => `${actor?.actorId || ''}:${actor?.patientId || ''}:${actor?.authEpoch ?? ''}:${!!actor?.unlocked}`

// Durable form drafts are isolated by doctor and patient. A restored form must be
// saved again; only this runtime's successful API + local write grants a binding.
export function createRegistrationDraft({ load, save: persist, saveProfile, identity }) {
  let current = '', key = '', form = empty(), saved = null, revision = 0, restored = false
  const pending = new Map()
  function sync() {
    const actor = identity(), next = binding(actor)
    if (next !== current) {
      current = next; saved = null; revision++; restored = false; form = empty()
      key = actor?.unlocked && actor.actorId && actor.patientId ? `collection_registration_draft_v1:${actor.actorId}:${actor.patientId}` : ''
      if (key) {
        const value = load(key)
        if (value) {
          const parsed = JSON.parse(value)
          if (parsed?.schema_version !== 1 || !parsed.form || typeof parsed.form !== 'object') throw Error('registration_storage')
          form = { ...empty(), ...parsed.form }; restored = true
        }
      }
    }
    return actor
  }
  const write = value => { if (!key) throw Error('registration_identity'); persist(key, JSON.stringify({ schema_version: 1, form: value })) }
  return {
    get value() { sync(); return clone(form) },
    invalidate() { current = ''; saved = null; revision++ },
    seed({ name, phone, gender, age, height_cm, weight_kg, shoe_size_eu }) {
      sync()
      if (!restored && key) {
        form = { ...empty(), name, phone, gender, age, height_cm, weight_kg, shoe_size_eu }
        restored = true
      }
    },
    edit(patch) {
      sync()
      if (!key) throw Error('registration_identity')
      saved = null; revision++; form = { ...form, ...patch }; write(form)
      return clone(form)
    },
    savedFor(patientId, actorId) {
      const actor = sync()
      return actor?.unlocked && actor.patientId === patientId && actor.actorId === actorId ? saved : null
    },
    save() {
      const actor = sync(), at = key, version = revision
      if (!at) return Promise.reject(Error('registration_identity'))
      const existing = pending.get(at)
      if (existing) {
        if (existing.version === version) return existing.promise
        return Promise.reject(Error('上次保存尚未完成，请稍后重试 / Previous save still pending'))
      }
      saved = null
      const promise = (async () => {
        const profile = normalizePatientProfile(form)
        if (!COLLECTION_TEST_TYPES.some(t => t.code === form.test_type)) throw Error('请选择测试类型 / Select test type')
        if (typeof form.remarks !== 'string' || form.remarks.length > 2000) throw Error('备注最多 2000 字 / Remarks: max 2000 characters')
        const testType = form.test_type, remarks = form.remarks
        const result = normalizePatientProfile(await saveProfile(profile, { ...actor }))
        sync()
        if (key !== at || revision !== version) throw Error('registration_changed')
        const persisted = { ...result, test_type: testType, remarks }
        write(persisted)
        form = persisted
        const { phone, ...snapshot } = result
        saved = freeze({ schema_version: 1, patient_id: actor.patientId, patient_snapshot: snapshot, test_type: testType, remarks })
        return saved
      })().finally(() => { pending.delete(at) })
      pending.set(at, { version, promise })
      return promise
    },
  }
}
