// 蓝牙uniapp/utils/apiShape.js —— 后端对象 <-> 前端形状 的纯映射
export function normalizePatient(b = {}) {
  return {
    id: b.id,
    subjectId: b.subject_id,
    name: b.name,
    phone: b.phone,
    gender: b.gender || '',
    age: b.age == null ? '' : b.age,
    lastAt: b.last_collected_at ? Date.parse(b.last_collected_at) : null,
    existed: !!b.existed
  }
}

export function buildRawDataPayload(patientId, apiData) {
  return { patient_id: patientId, ...apiData }
}

export function mapHistoryItem(it = {}) {
  return {
    id: it.id,
    foot: it.foot,
    collectedAt: it.collected_at ? Date.parse(it.collected_at) : null,
    pressure: [it.p1, it.p2, it.p3, it.p4, it.p5, it.p6, it.p7, it.p8, it.p9],
    ax: it.ax, ay: it.ay, az: it.az, gx: it.gx, gy: it.gy, gz: it.gz,
    stepLength: it.step_length, walkingSpeed: it.walking_speed,
    singleSupportTime: it.single_support_time, doubleSupportTime: it.double_support_time,
    t: it.transformed ? { ...it.transformed } : null
  }
}
