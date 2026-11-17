import { defineStore } from 'pinia'
import { store } from '@/store'
import { getPatients, setPatients, getCurrentPatientId, setCurrentPatientId, clearCurrentPatientId } from '@/utils/clinicStorage'
import { searchPatients, normalizePatientProfile } from '@/utils/patient'
import { normalizePatient } from '@/utils/apiShape'
import { createPatientApi, listPatientsApi, getPatientProfileApi, savePatientProfileApi } from '@/api'
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { createRegistrationDraft } from '@/utils/collectionRegistration'

const registrationRuntimes = new WeakMap()
const registrationActor = patientId => {
  const op = useOperatorStoreWithOut()
  return { actorId: op.operator?.clinicianId, patientId, authEpoch: op.authRuntime.authEpoch, unlocked: op.unlocked }
}
const requestIdentity = actor => ({ collectionIdentity: { clinicianId: actor.actorId, authEpoch: actor.authEpoch } })

export const usePatientStore = defineStore('patientStore', {
  state: () => ({
    patients: getPatients() || [],          // 后端患者的本地缓存（离线展示用）
    currentId: getCurrentPatientId() || null, // 后端 patient_id
    registrationState: { form: {}, ready: false, loading: false, saving: false, error: '' }
  }),
  getters: {
    current: (s) => s.patients.find((p) => p.id === s.currentId) || null,
    // 当前患者编号 = 后端 subjectId（如 #00427）
    currentSubjectId: (s) => {
      const p = s.patients.find((x) => x.id === s.currentId)
      return p ? p.subjectId : ''
    }
  },
  actions: {
    // V2 full-profile writes; a duplicate phone returns the existing profile.
    async create(input) {
      const res = await createPatientApi(normalizePatientProfile(input))
      const p = normalizePatient(res)
      const idx = this.patients.findIndex((x) => x.id === p.id)
      if (idx >= 0) this.patients.splice(idx, 1)
      this.patients = [p, ...this.patients]
      setPatients(this.patients)
      this.select(p.id)
      return p // p.existed 标记是否为查重命中
    },
    // 拉取当前医护患者列表（权威以后端为准，写入本地缓存）
    async loadList() {
      const res = await listPatientsApi()
      const cached = new Map(this.patients.map(patient => [patient.id, patient]))
      this.patients = (res || []).map(row => {
        const previous = cached.get(row.id)
        // The legacy list omits measurements returned by the V2 profile.
        const { height_cm, weight_kg, shoe_size_eu } = previous || {}
        return normalizePatient({ height_cm, weight_kg, shoe_size_eu, ...row })
      })
      setPatients(this.patients)
      return this.patients
    },
    registrationModel() {
      if (!registrationRuntimes.has(this)) registrationRuntimes.set(this, createRegistrationDraft({
        load: key => uni.getStorageSync(key), save: (key, value) => uni.setStorageSync(key, value),
        identity: () => registrationActor(this.currentId),
        saveProfile: (profile, actor) => savePatientProfileApi(actor.patientId, profile, requestIdentity(actor)),
      }))
      return registrationRuntimes.get(this)
    },
    savedRegistration(patientId = this.currentId, actorId = registrationActor(this.currentId).actorId) {
      return this.registrationModel().savedFor(patientId, actorId)
    },
    async prepareRegistration() {
      const actor = registrationActor(this.currentId), binding = JSON.stringify(actor)
      this.registrationState = { form: {}, ready: false, loading: true, saving: false, error: '' }
      const state = this.registrationState
      const current = () => this.registrationState === state && binding === JSON.stringify(registrationActor(this.currentId))
      try {
        const model = this.registrationModel()
        state.form = model.value
        if (!actor.unlocked || !actor.actorId || !actor.patientId) return
        const profile = normalizePatient(await getPatientProfileApi(actor.patientId, requestIdentity(actor)))
        if (!current()) return
        const index = this.patients.findIndex(p => p.id === actor.patientId)
        if (index >= 0) this.patients.splice(index, 1, profile)
        else this.patients.push(profile)
        setPatients(this.patients)
        model.seed(profile)
        state.form = model.value
        state.ready = !!model.savedFor(actor.patientId, actor.actorId)
      } catch (e) { if (current()) state.error = e.message || '资料读取失败 / Profile unavailable' }
      finally { if (current()) state.loading = false }
    },
    editRegistration(patch) {
      if (useBlueToothStoreWithOut().collectionState.active || this.registrationState.loading || this.registrationState.saving) return
      const model = this.registrationModel()
      this.registrationState.ready = false
      this.registrationState.error = ''
      try { model.edit(patch) }
      catch { this.registrationState.error = '草稿保存失败，请重试 / Draft storage failed' }
      this.registrationState.form = model.value
    },
    async saveRegistration() {
      if (useBlueToothStoreWithOut().collectionState.active || this.registrationState.loading || this.registrationState.saving) return
      const actor = registrationActor(this.currentId), binding = JSON.stringify(actor)
      const state = this.registrationState
      const current = () => this.registrationState === state && binding === JSON.stringify(registrationActor(this.currentId))
      state.saving = true; state.ready = false; state.error = ''
      try {
        const model = this.registrationModel()
        const result = await model.save()
        if (current() && model.savedFor(actor.patientId, actor.actorId) === result) {
          state.form = model.value
          state.ready = true
          const index = this.patients.findIndex(patient => patient.id === actor.patientId)
          if (index >= 0) {
            this.patients[index] = { ...this.patients[index], ...result.patient_snapshot, phone: state.form.phone }
          }
        }
        return result
      } catch (e) { if (current()) state.error = e.message || '登记保存失败 / Save failed' }
      finally { if (current()) state.saving = false }
    },
    select(id) {
      if (this.currentId !== id) {
        useBlueToothStoreWithOut().stopCollection('patient')
        registrationRuntimes.get(this)?.invalidate()
        this.registrationState = { form: {}, ready: false, loading: false, saving: false, error: '' }
      }
      this.currentId = id
      setCurrentPatientId(id)
    },
    clearCurrent() {
      useBlueToothStoreWithOut().stopCollection('patient')
      registrationRuntimes.get(this)?.invalidate()
      this.currentId = null
      this.registrationState = { form: {}, ready: false, loading: false, saving: false, error: '' }
      clearCurrentPatientId()
    },
    // 本地缓存按 lastAt 倒序 + 关键字过滤（离线展示）
    list(keyword) {
      const sorted = [...this.patients].sort((a, b) => (b.lastAt || 0) - (a.lastAt || 0))
      return searchPatients(sorted, keyword)
    }
  }
})

export function usePatientStoreWithOut() {
  return usePatientStore(store)
}
