// 蓝牙uniapp/api/patient.js
import { instance } from '@/utils'

export async function createPatientApi(data, custom) {
  return instance.request({ url: '/v2/patients', method: 'post', data, custom })
}
export async function getPatientProfileApi(id, custom) {
  return instance.request({ url: `/v2/patients/${id}/profile`, method: 'get', custom })
}
export async function savePatientProfileApi(id, data, custom) {
  return instance.request({ url: `/v2/patients/${id}/profile`, method: 'put', data, custom })
}
export async function listPatientsApi() {
  return instance.request({ url: '/patients', method: 'get' })
}
export async function getPatientApi(id) {
  return instance.request({ url: `/patients/${id}`, method: 'get' })
}
export async function getPatientHistoryApi(id, params = {}) {
  // params: { start, end, page, page_size }
  return instance.request({ url: `/patients/${id}/data`, method: 'get', params })
}
