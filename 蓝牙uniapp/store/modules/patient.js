import { defineStore } from 'pinia'
import { store } from '@/store'
import { getPatients, setPatients, getCurrentPatientId, setCurrentPatientId, clearCurrentPatientId } from '@/utils/clinicStorage'
import { searchPatients } from '@/utils/patient'
import { normalizePatient } from '@/utils/apiShape'
import { createPatientApi, listPatientsApi } from '@/api'

export const usePatientStore = defineStore('patientStore', {
  state: () => ({
    patients: getPatients() || [],          // 后端患者的本地缓存（离线展示用）
    currentId: getCurrentPatientId() || null // 后端 patient_id
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
    // 新建患者：POST /patients，用后端返回的 id/subject_id；命中查重则提示已选中
    async create({ name, phone, gender, age }) {
      const res = await createPatientApi({ name, phone, gender, age })
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
      this.patients = (res || []).map(normalizePatient)
      setPatients(this.patients)
      return this.patients
    },
    select(id) {
      this.currentId = id
      setCurrentPatientId(id)
    },
    clearCurrent() {
      this.currentId = null
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
