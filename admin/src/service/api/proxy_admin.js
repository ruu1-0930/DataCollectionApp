import ApiService from '../request';

/**
 * 登录
 * @param {*} data
 * @returns
 */
export function adminLoginApi(data) {
    return ApiService.post('/login', data);
}

/**
 * 信息查询
 * @param {*} data
 * @returns
 */
export function adminInfoApi(data) {
    return ApiService.post('/wjx_user/getUserInfo', data);
}

/**
 * 修改用户信息
 * @param {*} data
 * @returns
 */
export function updateUserInfoApi(data) {
    return ApiService.put('/user', data);
}

/**
 * 设备列表
 * @param {*} data
 * @returns
 */
export function getDeviceListApi(data) {
    return ApiService.get('/devices', data);
}

/**
 * 修改设备
 * @param {*} data
 * @returns
 */
export function updateDeviceApi(id, data) {
    return ApiService.put(`/devices/${id}`, data);
}

/**
 * 新增周计划
 * @param {*} data
 * @returns
 */
export function addWeeklyScheduleApi(data) {
    return ApiService.post('/weekly-schedules', data);
}

/**
 * 修改周计划
 * @param {*} data
 * @returns
 */
export function updateWeeklyScheduleApi(id, data) {
    return ApiService.put(`/weekly-schedules/${id}`, data);
}

/**
 * 查询周计划
 * @param {*} data
 * @returns
 */
export function queryWeeklyScheduleApi(data) {
    return ApiService.get('/weekly-schedules', data);
}

/**
 * 获取当天所有设备的原始数据及转换数据
 * @param {*} data
 * @returns
 */
export function getTodayDataApi(data) {
    return ApiService.get('/devices/raw_data/today', data);
}

/**
 * 获取所有设备中最新一条原始数据及转换数据
 * @param {*} data
 * @returns
 */
export function getLatestDataApi(data) {
    return ApiService.get('/devices/raw_data/latest', data);
}

/**
 * 根据时间范围获取原始数据及转换数据
 * @param {*} data
 * @returns
 */
export function getRangeDataApi(data) {
    return ApiService.get('/devices/data/range', data);
}

/**
 * 查询用户
 * @param {*} data
 * @returns
 */
export function queryUserApi(data) {
    return ApiService.get('/users', data);
}

// addUserApi
export function addUserApi(data) {
    return ApiService.post('/admin', data);
}