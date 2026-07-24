// 蓝牙uniapp/api/clinician.js
import { instance } from '@/utils'

export async function clinicianEnableApi(data) {
  // data: { hospital, dept, name, phone, passcode }
  return instance.request({ url: '/clinician/enable', method: 'post', data })
}
export async function clinicianLoginApi(data) {
  // data: { hospital, name, phone, passcode }
  return instance.request({ url: '/clinician/login', method: 'post', data })
}
export async function clinicianMeApi() {
  return instance.request({ url: '/clinician/me', method: 'get' })
}
export async function clinicianUpdateMeApi(data) {
  return instance.request({ url: '/clinician/me', method: 'put', data })
}
