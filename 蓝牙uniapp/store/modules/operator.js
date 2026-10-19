import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'
import { clearToken, setToken, getToken } from '@/utils/auth'
import { clinicianEnableApi, clinicianLoginApi } from '@/api'
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import {
  createOperatorSessionRuntime,
  enableOperatorSession,
  refreshOperatorSession,
  resetOperatorSession,
  unlockOperatorSession,
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
    enable(credentials) {
      useBlueToothStoreWithOut().endCollectionContext('identity')
      return enableOperatorSession({
        state: this,
        runtime: this.authRuntime,
        credentials,
        enableApi: clinicianEnableApi,
        setToken,
        setOperator,
      })
    },
    // 解锁必须经服务端重新验证；口令仅保留在当前运行期内存。
    unlock(passcode) {
      useBlueToothStoreWithOut().endCollectionContext('identity')
      return unlockOperatorSession({
        state: this,
        runtime: this.authRuntime,
        passcode,
        loginApi: clinicianLoginApi,
        setToken,
        setOperator,
      })
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
    hasToken() { return !!getToken() },
    reset() {
      useBlueToothStoreWithOut().endCollectionContext('identity')
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
