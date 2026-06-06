import { instance } from '@/utils'

/**
 * 用户登录
 * @param {*} data
 * @returns
 */
export async function userLoginApi(data) {
  return instance.request({
    url: '/login',
    method: 'post',
    data
  })
}

/**
 * 用户注册
 * @param {*} data
 * @returns
 */
export async function userRegisterApi(data) {
  return instance.request({
    url: '/register',
    method: 'post',
    data
  })
}

// 获取用户设备列表
export async function getUserDeviceListApi() {
  return instance.request({
    url: '/devices',
    method: 'get'
  })
}

// 新增设备列表
export async function addUserDeviceListApi(data) {
  return instance.request({
    url: '/devices',
    method: 'post',
    data
  })
}

// 头像上传
export async function userAvatarUploadApi(files) {
  return instance.upload('/upload_avatar', {
    files
  })
}
// put 修改用户信息/user
export async function userUpdateApi(data) {
  return instance.request({
    url: '/user',
    method: 'put',
    data
  })
}

// /devices/1 修改设备
export async function updateDeviceApi(id, data) {
  return instance.request({
    url: `/devices/${id}`,
    method: 'put',
    data
  })
}

// 发送设备原始数据
export async function sendDeviceRawDataApi(deviceCode, data) {
  return instance.request({
    url: `/devices/${deviceCode}/raw_data`,
    method: 'post',
    data
  })
}

// 获取设备数据
export async function getDeviceDataApi(deviceCode) {
  return instance.request({
    url: `/devices/${deviceCode}/data`,
    method: 'get'
  })
}

/**
 * 获取最新的T1、T2数据
 * @param {*} deviceCode
 * @returns
 */
export async function getDeviceLatestT1T2Api() {
  return instance.request({
    url: `/devices/latest_t1_t2`,
    method: 'get'
  })
}


// 获取当前用户本周T2、上一周T2、上一个月T3均值
export async function getUserT2T3Api() {
  return instance.request({
    url: '/devices/statistics',
    method: 'get'
  })
}



/**
 * 获取周计划
 * @returns 
 */
export async function getUserWeekPlanApi() {
  return instance.request({
    url: '/weekly-schedules',
    method: 'get'
  })
}

// delete /devices/1 删除设备
export async function deleteDeviceApi(id) {
  return instance.request({
    url: `/devices/${id}`,
    method: 'delete'
  })
}


export async function getDeviceDailyAveragesApi() {
  return instance.request({
    url: '/devices/daily_averages',
    method: 'get'
  })
}