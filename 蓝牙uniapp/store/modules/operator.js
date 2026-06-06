import { defineStore } from 'pinia'
import { store } from '@/store'
import { getOperator, setOperator, clearOperator } from '@/utils/clinicStorage'

export const useOperatorStore = defineStore('operatorStore', {
  state: () => ({
    operator: getOperator() || null, // { hospital, dept, name, phone, passcode, enabled }
    unlocked: false                  // 本次启动是否已解锁（不持久化）
  }),
  getters: {
    isEnabled: (s) => !!(s.operator && s.operator.enabled)
  },
  actions: {
    // 首次启用：保存档案 + 口令，并视为已解锁
    enable({ hospital, dept, name, phone, passcode }) {
      this.operator = { hospital, dept, name, phone, passcode, enabled: true }
      setOperator(this.operator)
      this.unlocked = true
    },
    // 解锁校验
    unlock(passcode) {
      if (this.operator && passcode === this.operator.passcode) {
        this.unlocked = true
        return true
      }
      return false
    },
    // 重新启用本机（清档案，回到启用页）
    reset() {
      this.operator = null
      this.unlocked = false
      clearOperator()
    },
    // 采集归属信息（写入采集数据用）
    attribution() {
      const o = this.operator || {}
      return { hospital: o.hospital, dept: o.dept, doctor: o.name }
    }
  }
})

export function useOperatorStoreWithOut() {
  return useOperatorStore(store)
}
