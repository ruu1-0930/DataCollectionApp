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

export async function createCollectionApi(data, collectionIdentity) {
  return instance.request({ url: '/collection-sessions', method: 'post', data, custom: { collectionIdentity } })
}
export async function uploadCollectionBatchApi(captureId, data, collectionIdentity) {
  return instance.request({ url: `/collection-sessions/${captureId}/batches`, method: 'post', data, custom: { collectionIdentity } })
}
export async function stopCollectionApi(captureId, data, collectionIdentity) {
  return instance.request({ url: `/collection-sessions/${captureId}/stop`, method: 'post', data, custom: { collectionIdentity } })
}
