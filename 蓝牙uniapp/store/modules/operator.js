import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'
import { buildEnableCredentials } from '@/utils/clinicianCredentials'
import { clearToken, setToken, getToken } from '@/utils/auth'
import { clinicianEnableApi, clinicianLoginApi } from '@/api'
import {
  authenticateOperator,
  buildPersistentOperator,
  createOperatorSessionRuntime,
  refreshOperatorSession,
  resetOperatorSession,
} from '@/utils/operatorSession'

export const useOperatorStore = defineStore('operatorStore', {
  state: () => ({
    operator: getOperator() || null, // { hospital, dept, name, phone, enabled, clinicianId }
    runtimePasscode: null,
    unlocked: false,
    authRuntime: createOperatorSessionRuntime(),
  }),
  getters: {
    isEnabled: (s) => !!(s.operator && s.operator.enabled)
  },
  actions: {
    // 首次启用：POST /clinician/enable → 存 token + 本地档案
    async enable({ hospital, dept, name, phone, passcode }) {
      const authEpoch = this.authRuntime.authEpoch
      const res = await clinicianEnableApi(buildEnableCredentials({
        hospital, dept, name, phone, passcode
      }))
      if (!this.isCurrentAuthEpoch(authEpoch)) return null
      setToken(`Bearer ${res.token}`)
      this.operator = buildPersistentOperator({
        hospital, dept, name, phone, enabled: true,
      }, res.clinician)
      setOperator(this.operator)
      this.runtimePasscode = passcode
      this.unlocked = true
      return res
    },
    // 解锁必须经服务端重新验证；口令仅保留在当前运行期内存。
    async unlock(passcode) {
      const authEpoch = this.authRuntime.authEpoch
      const authenticated = await authenticateOperator({
        operator: this.operator,
        passcode,
        loginApi: clinicianLoginApi,
      })
      if (!this.isCurrentAuthEpoch(authEpoch)) return false
      setToken(authenticated.token)
      this.operator = authenticated.operator
      setOperator(this.operator)
      this.runtimePasscode = passcode
      this.unlocked = true
      return true
    },
    // 静默换 token：仅使用本运行期已验证的口令。
    refreshToken() {
      return refreshOperatorSession({
        state: this,
        runtime: this.authRuntime,
        loginApi: clinicianLoginApi,
        setToken,
        setOperator,
      })
    },
    isCurrentAuthEpoch(authEpoch) { return this.authRuntime.authEpoch === authEpoch },
    hasToken() { return !!getToken() },
    reset() {
      resetOperatorSession({
        state: this,
        runtime: this.authRuntime,
        clearOperator,
        clearToken,
      })
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
