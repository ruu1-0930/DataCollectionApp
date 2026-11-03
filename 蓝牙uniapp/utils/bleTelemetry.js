const fields = [
  ...Array.from({ length: 9 }, (_, i) => `lp${i + 1}`), 'ax', 'ay', 'az', 'gx', 'gy', 'gz',
  'left_step_size', 'left_speed', 'left_single_sp_time', 'left_double_sp_time',
  ...Array.from({ length: 9 }, (_, i) => `rp${i + 1}`), 'right_ax', 'right_ay', 'right_az', 'right_gx', 'right_gy', 'right_gz',
  'right_step_size', 'right_speed', 'right_single_sp_time', 'right_double_sp_time',
]
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/
function protocolError(details = {}) {
  const error = new Error('protocol')
  // Retain only field positions/counts, never rejected sensor or location text.
  for (const key of Object.keys(details)) error[key] = details[key]
  return error
}
function number(text, optional = false, fieldIndex = 0) {
  if (text === '' && optional) return null
  if (!decimal.test(text) || !Number.isFinite(Number(text))) throw protocolError({ fieldIndex })
  return Number(text)
}
function integer(text, fieldIndex) {
  if (!/^\d+$/.test(text) || !Number.isSafeInteger(Number(text))) throw protocolError({ fieldIndex })
  return Number(text)
}

export function parseTelemetry(line) {
  const parts = line.split(',')
  if (parts[0] === 'GPS1') {
    if (parts.length !== 13) throw protocolError({ fieldCount: parts.length })
    if (line.length > 1024 || /[\r\n]/.test(line)) throw protocolError({ reason: 'line' })
    if (!['0', '1'].includes(parts[2])) throw protocolError({ fieldIndex: 3 })
    // Firmware uses the exact token "nan" for unavailable no-fix measurements.
    // Keep raw_line intact; JSON/UI values use null rather than IEEE NaN or zero.
    const gpsNumber = index => parts[2] === '0' && parts[index] === 'nan' ? null : number(parts[index], true, index + 1)
    const gps = { seq: integer(parts[1], 2), fix: parts[2] === '1', lat: gpsNumber(3), lon: gpsNumber(4),
      alt: gpsNumber(5), speed: gpsNumber(6), sats: integer(parts[7], 8), hdop: gpsNumber(8),
      age: integer(parts[9], 10), utc: parts[10], chars: integer(parts[11], 12), errors: integer(parts[12], 13) }
    return { stream: 'gps', payload: { raw_line: line }, gps }
  }
  if (parts.length !== 38) throw new Error('protocol')
  const payload = {}
  fields.forEach((key, i) => { payload[key] = number(parts[i]) })
  return { stream: 'insole', payload }
}

export function createBleLines(onLine, onError = () => {}, now = Date.now) {
  let pending = '', discarding = false
  return {
    reset() { pending = ''; discarding = false },
    push(input) {
      const data = input instanceof ArrayBuffer || Array.isArray(input) ? new Uint8Array(input)
        : new Uint8Array(input.buffer, input.byteOffset, input.byteLength)
      for (const byte of data) {
        if (byte === 10) {
          if (!discarding) onLine(pending.replace(/\r$/, ''), now())
          pending = ''; discarding = false
        } else if (!discarding) {
          pending += String.fromCharCode(byte)
          if (pending.length > 65536) { pending = ''; discarding = true; onError('line_overflow') }
        }
      }
    },
  }
}
