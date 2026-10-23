const fail = () => { throw new Error('protocol') }
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === keys.length && keys.every(k => Object.prototype.hasOwnProperty.call(v, k))
const integer = (v, min, max) => Number.isSafeInteger(v) && v >= min && v <= max
export function parseRadarPayload(value) {
  let p = value
  if (typeof p === 'string') { try { p = JSON.parse(p) } catch { fail() } }
  if (!exact(p, ['frames', 'bytes', 'age_ms', 'stale', 'targets']) ||
    !integer(p.frames, 0, Number.MAX_SAFE_INTEGER) || !integer(p.bytes, 0, Number.MAX_SAFE_INTEGER) ||
    !(p.age_ms === null || (typeof p.age_ms === 'number' && Number.isFinite(p.age_ms) && p.age_ms >= 0)) ||
    typeof p.stale !== 'boolean' || !Array.isArray(p.targets) || p.targets.length > 3) fail()
  const slots = new Set()
  for (const t of p.targets) {
    if (!exact(t, ['slot', 'present', 'x_mm', 'y_mm', 'speed_cms', 'resolution_mm']) || !integer(t.slot, 1, 3) || slots.has(t.slot) ||
      typeof t.present !== 'boolean' || !['x_mm', 'y_mm', 'speed_cms'].every(k => integer(t[k], -32767, 32767)) || !integer(t.resolution_mm, 0, 65535)) fail()
    slots.add(t.slot)
  }
  return JSON.parse(JSON.stringify(p))
}
export function visibleRadarTargets(p) {
  return p && p.frames > 0 && !p.stale && p.age_ms !== null && p.age_ms <= 1500 ? p.targets.filter(t => t.present) : []
}
export function isPrivateIPv4(ip) {
  if (typeof ip !== 'string' || !/^(0|[1-9]\d{0,2})(\.(0|[1-9]\d{0,2})){3}$/.test(ip)) return false
  const p = ip.split('.').map(Number)
  return p.every(v => v <= 255) && (p[0] === 10 || p[0] === 172 && p[1] >= 16 && p[1] <= 31 || p[0] === 192 && p[1] === 168)
}
