// 蓝牙uniapp/api/patient.js
import { instance } from '@/utils'

export async function createPatientApi(data) {
  // data: { name, phone, gender, age }
  return instance.request({ url: '/patients', method: 'post', data })
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
