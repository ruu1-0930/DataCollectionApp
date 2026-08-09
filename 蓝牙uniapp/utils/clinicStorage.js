// utils/clinicStorage.js —— 操作员档案 / 患者列表 / 当前患者 的本地持久化
import { sanitizeOperatorProfile } from './clinicianCredentials'

const OPERATOR_KEY = '__operator__'   // { hospital, dept, name, phone, passcode, enabled, clinicianId }
const PATIENTS_KEY = '__patients__'   // [ { seq, name, phone, gender, age, createdAt, lastAt, count } ]
const CURRENT_KEY  = '__current_patient_id__' // 后端 patient_id

export function getOperator() {
  try {
    const stored = uni.getStorageSync(OPERATOR_KEY) || null
    const sanitized = sanitizeOperatorProfile(stored)
    if (sanitized !== stored) uni.setStorageSync(OPERATOR_KEY, sanitized)
    return sanitized
  } catch (e) { return null }
}
export function setOperator(op) { uni.setStorageSync(OPERATOR_KEY, op) }
export function clearOperator() { uni.removeStorageSync(OPERATOR_KEY) }

export function getPatients() {
  try { return uni.getStorageSync(PATIENTS_KEY) || [] } catch (e) { return [] }
}
export function setPatients(list) { uni.setStorageSync(PATIENTS_KEY, list || []) }

export function getCurrentPatientId() {
  try { return uni.getStorageSync(CURRENT_KEY) || null } catch (e) { return null }
}
export function setCurrentPatientId(id) { uni.setStorageSync(CURRENT_KEY, id) }
export function clearCurrentPatientId() { uni.removeStorageSync(CURRENT_KEY) }
