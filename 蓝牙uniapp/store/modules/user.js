import { defineStore } from 'pinia'
import { store } from '@/store'
import { userLoginApi, userUpdateApi } from '@/api'
import { setToken, setUser, getUser, getToken } from '@/utils/auth'
import { useBlueToothStoreWithOut } from './blueTooth'

export const useUserStore = defineStore('userStore', {
  state: () => {
    return {
      user: getUser() || {},
      token: getToken() || ''
    }
  },
  getters: {},
  actions: {
    async userLogin(data) {
      uni.showLoading({
        title: '登录中'
      })
      
      try {
        const res = await userLoginApi(data)
        this.user = res
        this.token = `Bearer ${res.token}`
        setUser(this.user)
        setToken(this.token)
        const blueToothStore = useBlueToothStoreWithOut()
        // 设置设备列表
        await blueToothStore.getDevicesList()
        uni.showToast({
          title: '登录成功',
          icon: 'success'
        })
        uni.hideLoading()
        return res
      } catch (error) {
        uni.hideLoading()
        console.error('登录API调用失败:', error)
        // 重新抛出错误，让调用方处理
        throw error
      }
    },
    // 旧登录模型遗留：新临床模型不再使用 App 登录态，此方法已无调用方。
    // 仅清理用户态，不再清空全部存储（避免误删操作员/患者本地数据）、不再跳登录页。
    logout() {
      this.user = {}
      this.token = ''
    },

    /**
     * 修改用户信息
     * @param {*} data
     */
    async updateUserInfo(data) {
      const res = await userUpdateApi(data)
      this.user = res
      setUser(this.user)
    }
  }
})

export function useUserStoreWithOut() {
  return useUserStore(store)
}
