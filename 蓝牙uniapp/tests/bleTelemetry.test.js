import { describe, expect, it } from 'vitest'
import { createBleLines, parseTelemetry } from '../utils/bleTelemetry'

const insole = Array.from({ length: 38 }, (_, i) => i + 1).join(',')
const gps = 'GPS1,8,0,,,,,0,,4294967295,,12,0'
const bytes = s => Uint8Array.from([...s].map(c => c.charCodeAt(0)))

describe('BLE text stream', () => {
  it('reassembles every byte split and preserves independent stream values', () => {
    const text = insole + '\r\n' + gps + '\n' + insole + '\n'
    for (let i = 0; i <= text.length; i++) {
      const rows = []
      const stream = createBleLines((line, time) => rows.push([parseTelemetry(line), time]), () => {}, () => 123)
      stream.push(bytes(text.slice(0, i)))
      stream.push(bytes(text.slice(i)))
      expect(rows.map(r => r[0].stream)).toEqual(['insole', 'gps', 'insole'])
      expect(rows[0][0].payload.left_speed).toBe(17)
      expect(rows[1][0].gps.speed).toBe(null)
      expect(rows.every(r => r[1] === 123)).toBe(true)
    }
  })
  it('drops an overlong row through LF and never accepts its suffix', () => {
    const rows = [], errors = []
    const stream = createBleLines(line => rows.push(line), e => errors.push(e))
    stream.push(bytes('x'.repeat(65537)))
    stream.push(bytes(insole + '\n' + gps + '\n'))
    expect(rows).toEqual([gps])
    expect(errors).toHaveLength(1)
  })
  it('clears partial lines at disconnect and continues after malformed rows', () => {
    const rows = []
    const stream = createBleLines(line => rows.push(line))
    stream.push(bytes('GPS1,8,'))
    stream.reset()
    stream.push(bytes(insole + '\n'))
    expect(rows).toEqual([insole])
    expect(() => parseTelemetry('1,'.repeat(37) + '2garbage')).toThrow()
    expect(() => parseTelemetry(insole.replace('1,', 'Infinity,'))).toThrow()
  })
})
describe('GPS1 raw protocol', () => {
  it('keeps no-fix empty fields and out-of-range coordinates without quality rescoring', () => {
    expect(parseTelemetry(gps).gps).toMatchObject({ fix: false, lat: null, lon: null, speed: null, utc: '' })
    const line = 'GPS1,9,1,100,181,3,2.7,4,8,200,120000,50,0'
    const parsed = parseTelemetry(line)
    expect(parsed.payload).toEqual({ raw_line: line })
    expect(parsed.gps).toMatchObject({ lat: 100, lon: 181, speed: 2.7 })
    expect(parsed.gps).not.toHaveProperty('quality')
  })
  it.each([
    'GPS1,-1,0,,,,,0,,0,,0,0', 'GPS1,1.5,0,,,,,0,,0,,0,0',
    'GPS1,9007199254740992,0,,,,,0,,0,,0,0', 'GPS1,1,2,,,,,0,,0,,0,0',
    'GPS1,1,0,NaN,,,,0,,0,,0,0', 'GPS1,1,0,,,,,1x,,0,,0,0',
  ])('rejects malformed GPS without accepting partial numeric text: %s', line => {
    expect(() => parseTelemetry(line)).toThrow()
  })
})
