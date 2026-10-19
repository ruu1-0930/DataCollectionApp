const fields = [
  ...Array.from({ length: 9 }, (_, i) => `lp${i + 1}`), 'ax', 'ay', 'az', 'gx', 'gy', 'gz',
  'left_step_size', 'left_speed', 'left_single_sp_time', 'left_double_sp_time',
  ...Array.from({ length: 9 }, (_, i) => `rp${i + 1}`), 'right_ax', 'right_ay', 'right_az', 'right_gx', 'right_gy', 'right_gz',
  'right_step_size', 'right_speed', 'right_single_sp_time', 'right_double_sp_time',
]
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/
function number(text, optional = false) {
  if (text === '' && optional) return null
  if (!decimal.test(text) || !Number.isFinite(Number(text))) throw new Error('protocol')
  return Number(text)
}
function integer(text) {
  if (!/^\d+$/.test(text) || !Number.isSafeInteger(Number(text))) throw new Error('protocol')
  return Number(text)
}

export function parseTelemetry(line) {
  const parts = line.split(',')
  if (parts[0] === 'GPS1') {
    if (parts.length !== 13 || line.length > 1024 || /[\r\n]/.test(line) || !['0', '1'].includes(parts[2])) throw new Error('protocol')
    const gps = { seq: integer(parts[1]), fix: parts[2] === '1', lat: number(parts[3], true), lon: number(parts[4], true),
      alt: number(parts[5], true), speed: number(parts[6], true), sats: integer(parts[7]), hdop: number(parts[8], true),
      age: integer(parts[9]), utc: parts[10], chars: integer(parts[11]), errors: integer(parts[12]) }
    return { stream: 'gps', payload: { raw_line: line }, gps }
  }
  if (parts.length !== 38) throw new Error('protocol')
  return { stream: 'insole', payload: Object.fromEntries(fields.map((key, i) => [key, number(parts[i])])) }
}

export function createBleLines(onLine, onError = () => {}, now = Date.now) {
  let pending = '', discarding = false
  return {
    reset() { pending = ''; discarding = false },
    push(input) {
      const data = input instanceof ArrayBuffer ? new Uint8Array(input)
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
