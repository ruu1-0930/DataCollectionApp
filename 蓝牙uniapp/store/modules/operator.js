import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'
import { buildEnableCredentials, buildLoginCredentials } from '@/utils/clinicianCredentials'
import { setToken, getToken } from '@/utils/auth'
import { clinicianEnableApi, clinicianLoginApi } from '@/api'

export const useOperatorStore = defineStore('operatorStore', {
  state: () => ({
    operator: getOperator() || null, // { hospital, dept, name, phone, passcode, enabled, clinicianId }
    unlocked: false
  }),
  getters: {
    isEnabled: (s) => !!(s.operator && s.operator.enabled)
  },
  actions: {
    // 首次启用：POST /clinician/enable → 存 token + 本地档案
    async enable({ hospital, dept, name, phone, passcode }) {
      const res = await clinicianEnableApi(buildEnableCredentials({
        hospital, dept, name, phone, passcode
      }))
      setToken(`Bearer ${res.token}`)
      this.operator = {
        hospital, dept, name, phone, passcode, enabled: true,
        clinicianId: res.clinician.id
      }
      setOperator(this.operator)
      this.unlocked = true
      return res
    },
    // 本地解锁（离线可用，纯本地比对，保留）
    unlock(passcode) {
      if (this.operator && passcode === this.operator.passcode) {
        this.unlocked = true
        return true
      }
      return false
    },
    // 静默换 token：用本地凭证调 /clinician/login，不弹登录页
    async refreshToken() {
      const o = this.operator
      if (!o || !o.passcode) throw new Error('未启用，无法刷新 token')
      const res = await clinicianLoginApi(buildLoginCredentials(o))
      setToken(`Bearer ${res.token}`)
      this.operator = {
        hospital: o.hospital,
        dept: o.dept,
        name: o.name,
        phone: o.phone,
        passcode: o.passcode,
        enabled: o.enabled,
        clinicianId: res.clinician.id
      }
      setOperator(this.operator)
      return res
    },
    hasToken() { return !!getToken() },
    reset() {
      this.operator = null
      this.unlocked = false
      clearOperator()
    },
    attribution() {
      const o = this.operator || {}
      return { hospital: o.hospital, dept: o.dept, doctor: o.name }
    }
  }
})

export function useOperatorStoreWithOut() {
  return useOperatorStore(store)
}
