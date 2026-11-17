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
const emptyProfile = { name: '', phone: null, gender: '', age: null, height_cm: null, weight_kg: null, shoe_size_eu: null }
const profileFields = Object.keys(emptyProfile)
const quantities = ['age', 'height_cm', 'weight_kg', 'shoe_size_eu']
const canonical = (field, value) => {
  const text = String(value ?? '').trim()
  if (!text) return null
  const number = Number(text)
  return quantities.includes(field) && Number.isFinite(number) ? number : text
}
const same = (field, left, right) => canonical(field, left) === canonical(field, right)
const binding = actor => `${actor?.actorId || ''}:${actor?.patientId || ''}:${actor?.authEpoch ?? ''}:${!!actor?.unlocked}`

// Durable form drafts are isolated by doctor and patient. A restored form must be
// saved again; only this runtime's successful API + local write grants a binding.
export function createRegistrationDraft({ load, save: persist, saveProfile, identity }) {
  let current = '', key = '', saved = null, revision = 0
  let profile = null, edits = {}, testType = '', remarks = ''
  const pending = new Map()
  function sync() {
    const actor = identity(), next = binding(actor)
    if (next !== current) {
      current = next; saved = null; revision++
      profile = null; edits = {}; testType = ''; remarks = ''
      key = actor?.unlocked && actor.actorId && actor.patientId ? `collection_registration_draft_v1:${actor.actorId}:${actor.patientId}` : ''
      if (key) {
        const value = load(key)
        if (value) {
          const parsed = JSON.parse(value)
          if (parsed?.schema_version !== 1 || !parsed.edits || typeof parsed.edits !== 'object') throw Error('无法读取登记草稿')
          edits = parsed.edits; testType = parsed.test_type; remarks = parsed.remarks
        }
      }
    }
    return actor
  }
  function form() {
    const value = { ...emptyProfile, ...profile, test_type: testType, remarks }
    for (const field of profileFields) if (edits[field]) value[field] = edits[field].value
    return value
  }
  function conflicts() {
    if (!profile) return []
    return profileFields.filter(field => edits[field] && !same(field, edits[field].base, profile[field]) &&
      !same(field, edits[field].value, profile[field])).map(field => ({ field, serverValue: profile[field] }))
  }
  function write(changes = edits) {
    persist(key, JSON.stringify({ schema_version: 1, edits: changes, test_type: testType, remarks }))
  }
  return {
    get value() { sync(); return clone(form()) },
    get conflicts() { sync(); return conflicts() },
    invalidate() { current = ''; saved = null; revision++ },
    seed({ name, phone, gender, age, height_cm, weight_kg, shoe_size_eu }) {
      sync()
      if (!key) return
      const next = { name, phone, gender, age, height_cm, weight_kg, shoe_size_eu }
      if (profile && profileFields.some(field => !same(field, profile[field], next[field]))) { saved = null; revision++ }
      for (const field of profileFields) {
        const edit = edits[field]
        if (edit && same(field, edit.base, edit.value) && !same(field, edit.base, next[field])) delete edits[field]
      }
      profile = next
    },
    edit(patch) {
      sync()
      if (!key) throw Error('请先解锁并选择患者')
      saved = null; revision++
      for (const field of profileFields) {
        if (!Object.prototype.hasOwnProperty.call(patch, field)) continue
        const value = patch[field], latest = profile?.[field] ?? null
        const base = same(field, value, latest) || !edits[field] ? latest : edits[field].base
        edits[field] = { base, value }
      }
      if (typeof patch.test_type === 'string') testType = patch.test_type
      if (typeof patch.remarks === 'string') remarks = patch.remarks
      write()
      return clone(form())
    },
    resolve(field, keepLocal) {
      sync()
      if (!conflicts().some(conflict => conflict.field === field)) return
      const next = { ...edits }
      if (keepLocal) next[field] = { ...next[field], base: profile[field] }
      else delete next[field]
      write(next)
      edits = next; saved = null; revision++
    },
    savedFor(patientId, actorId) {
      const actor = sync()
      return actor?.unlocked && actor.patientId === patientId && actor.actorId === actorId ? saved : null
    },
    save() {
      const actor = sync(), at = key, version = revision
      if (!at) return Promise.reject(Error('请先解锁并选择患者'))
      const existing = pending.get(at)
      if (existing) {
        if (existing.version === version) return existing.promise
        return Promise.reject(Error('上次保存尚未完成，请稍后重试'))
      }
      saved = null
      const promise = (async () => {
        if (!profile) throw Error('请先读取患者资料')
        if (conflicts().length) throw Error('患者资料有冲突，请逐项选择后再保存')
        const input = normalizePatientProfile(form())
        if (!COLLECTION_TEST_TYPES.some(t => t.code === testType)) throw Error('请选择测试类型')
        if (typeof remarks !== 'string' || remarks.length > 2000) throw Error('备注最多 2000 字')
        const result = normalizePatientProfile(await saveProfile(input, { ...actor }))
        sync()
        if (key !== at || revision !== version) throw Error('registration_changed')
        write({})
        profile = result; edits = {}
        const { phone, ...snapshot } = result
        saved = freeze({ schema_version: 1, patient_id: actor.patientId, patient_snapshot: snapshot, test_type: testType, remarks })
        return saved
      })().finally(() => { pending.delete(at) })
      pending.set(at, { version, promise })
      return promise
    },
  }
}
