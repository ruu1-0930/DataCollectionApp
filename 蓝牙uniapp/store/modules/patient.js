import { defineStore } from 'pinia'
import { store } from '@/store'
import { getPatients, setPatients, getCurrentSeq, setCurrentSeq, clearCurrentSeq } from '@/utils/clinicStorage'
import { nextSeq, formatSubjectId, searchPatients } from '@/utils/patient'

export const usePatientStore = defineStore('patientStore', {
  state: () => ({
    patients: getPatients() || [],
    currentSeq: getCurrentSeq() || null
  }),
  getters: {
    current: (s) => s.patients.find((p) => p.seq === s.currentSeq) || null,
    currentId: (s) => {
      const p = s.patients.find((x) => x.seq === s.currentSeq)
      return p ? formatSubjectId(p.seq) : ''
    }
  },
  actions: {
    // 新建患者并设为当前，返回新患者
    create({ name, phone, gender, age }) {
      const seq = nextSeq(this.patients)
      const now = Date.now()
      const p = { seq, name, phone, gender: gender || '', age: age || '', createdAt: now, lastAt: now, count: 0 }
      this.patients = [p, ...this.patients]
      setPatients(this.patients)
      this.select(seq)
      return p
    },
    select(seq) {
      this.currentSeq = seq
      setCurrentSeq(seq)
    },
    clearCurrent() {
      this.currentSeq = null
      clearCurrentSeq()
    },
    // 列表（按 lastAt 倒序）+ 关键字过滤
    list(keyword) {
      const sorted = [...this.patients].sort((a, b) => (b.lastAt || 0) - (a.lastAt || 0))
      return searchPatients(sorted, keyword)
    }
  }
})

export function usePatientStoreWithOut() {
  return usePatientStore(store)
}
