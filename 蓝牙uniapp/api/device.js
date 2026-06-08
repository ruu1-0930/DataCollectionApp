// 蓝牙uniapp/api/device.js
import { instance } from '@/utils'

export async function registerDeviceApi(data) {
  // data: { device_code, device_name? }
  return instance.request({ url: '/devices', method: 'post', data })
}
export async function listDevicesApi() {
  return instance.request({ url: '/devices', method: 'get' })
}
export async function deleteDeviceApi(id) {
  return instance.request({ url: `/devices/${id}`, method: 'delete' })
}
export async function uploadRawDataApi(deviceCode, data) {
  // data: { patient_id, ...apiData(38 维) }
  return instance.request({ url: `/devices/${deviceCode}/raw_data`, method: 'post', data })
}
