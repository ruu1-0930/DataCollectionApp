// 蓝牙uniapp/tests/apiShape.test.js
import { describe, it, expect } from 'vitest'
import { normalizePatient, buildRawDataPayload, mapHistoryItem } from '../utils/apiShape.js'

describe('normalizePatient', () => {
  it('后端患者对象映射为前端形状', () => {
    const p = normalizePatient({
      id: 7, subject_id: '#00007', name: '张三', phone: '13812346543',
      gender: '男', age: 60, last_collected_at: '2026-06-07T03:00:00', existed: true
    })
    expect(p).toEqual({
      id: 7, subjectId: '#00007', name: '张三', phone: '13812346543',
      gender: '男', age: 60, lastAt: Date.parse('2026-06-07T03:00:00'), existed: true
    })
  })
  it('缺省字段安全降级', () => {
    const p = normalizePatient({ id: 1, subject_id: '#00001' })
    expect(p.gender).toBe('')
    expect(p.age).toBe('')
    expect(p.lastAt).toBe(null)
    expect(p.existed).toBe(false)
  })
})

describe('buildRawDataPayload', () => {
  it('把 patient_id 并入 38 维 apiData', () => {
    const payload = buildRawDataPayload(7, { ax: 1, ay: 2, lp1: 9 })
    expect(payload).toEqual({ patient_id: 7, ax: 1, ay: 2, lp1: 9 })
  })
})

describe('mapHistoryItem', () => {
  it('映射历史记录与 transformed', () => {
    const it = mapHistoryItem({
      id: 11, foot: 'R', collected_at: '2026-06-07T03:00:00',
      p1: 1, p2: 2, p3: 3, p4: 4, p5: 5, p6: 6, p7: 7, p8: 8, p9: 9,
      ax: 1, ay: 2, az: 3, gx: 4, gy: 5, gz: 6,
      step_length: 16, walking_speed: 17, single_support_time: 18, double_support_time: 19,
      transformed: { T1: 1, T2: 2, T3: 3, T4: 4, T5: 5 }
    })
    expect(it.id).toBe(11)
    expect(it.foot).toBe('R')
    expect(it.collectedAt).toBe(Date.parse('2026-06-07T03:00:00'))
    expect(it.pressure).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9])
    expect(it.stepLength).toBe(16)
    expect(it.doubleSupportTime).toBe(19)
    expect(it.t).toEqual({ T1: 1, T2: 2, T3: 3, T4: 4, T5: 5 })
  })
  it('transformed 缺省为 null', () => {
    expect(mapHistoryItem({ id: 1, transformed: null }).t).toBe(null)
  })
})
