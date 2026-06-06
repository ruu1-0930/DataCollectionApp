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
    logout() {
      this.user = {}
      this.token = ''
      uni.clearStorage()
      uni.redirectTo({
        url: '/pages/login/login'
      })
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
