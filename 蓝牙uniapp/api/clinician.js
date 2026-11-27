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
export async function clinicianMeApi(identity) {
  return instance.request({ url: '/clinician/me', method: 'get', custom: { collectionIdentity: identity } })
}
export async function clinicianUpdateMeApi(data, identity) {
  return instance.request({ url: '/clinician/me', method: 'put', data, custom: { collectionIdentity: identity } })
}
