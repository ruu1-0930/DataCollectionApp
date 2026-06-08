// utils/patient.js —— 患者相关纯逻辑，可单测
// 编号方案：系统自动假名 subject_id，格式 #00001（5 位补零）
export function formatSubjectId(seq) {
  const n = Math.max(0, Math.floor(Number(seq) || 0))
  return '#' + String(n).padStart(5, '0')
}

// 根据已有最大序号生成下一个序号
export function nextSeq(patients) {
  const max = (patients || []).reduce((m, p) => Math.max(m, p.seq || 0), 0)
  return max + 1
}

// 手机号脱敏：138****6543（非 11 位原样返回）
export function maskPhone(phone) {
  const s = String(phone || '').replace(/\s/g, '')
  if (s.length !== 11) return s
  return s.slice(0, 3) + '****' + s.slice(7)
}

// 11 位手机号校验
export function isValidPhone(phone) {
  return /^1\d{10}$/.test(String(phone || '').trim())
}

// 新建患者字段校验，返回 { ok, msg }
export function validatePatient({ name, phone } = {}) {
  if (!name || !String(name).trim()) return { ok: false, msg: '请输入患者姓名' }
  if (!isValidPhone(phone)) return { ok: false, msg: '请输入正确的 11 位手机号' }
  return { ok: true, msg: '' }
}

// 搜索：按 姓名 / 手机号 / 编号(数字或#) 匹配，返回过滤后的列表
export function searchPatients(patients, keyword) {
  const k = String(keyword || '').trim().toLowerCase()
  if (!k) return patients || []
  const kDigits = k.replace(/[^0-9]/g, '')
  return (patients || []).filter((p) => {
    const name = String(p.name || '').toLowerCase()
    const phone = String(p.phone || '')
    // 后端患者带 subjectId（#00007）；旧本地对象回退用 seq 计算
    const id = String(p.subjectId || formatSubjectId(p.seq)).toLowerCase()
    const idDigits = id.replace(/[^0-9]/g, '')
    if (name.includes(k)) return true
    if (kDigits && phone.includes(kDigits)) return true
    if (id.includes(k)) return true
    if (kDigits && idDigits.includes(kDigits)) return true
    return false
  })
}
