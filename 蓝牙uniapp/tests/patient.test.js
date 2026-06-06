import { describe, it, expect } from 'vitest'
import {
  formatSubjectId, nextSeq, maskPhone, isValidPhone, validatePatient, searchPatients
} from '../utils/patient.js'

describe('formatSubjectId', () => {
  it('补零到 5 位并带 #', () => {
    expect(formatSubjectId(427)).toBe('#00427')
    expect(formatSubjectId(1)).toBe('#00001')
  })
})

describe('nextSeq', () => {
  it('返回最大 seq + 1', () => {
    expect(nextSeq([{ seq: 3 }, { seq: 7 }, { seq: 5 }])).toBe(8)
    expect(nextSeq([])).toBe(1)
  })
})

describe('maskPhone', () => {
  it('脱敏中间四位', () => {
    expect(maskPhone('13812346543')).toBe('138****6543')
  })
  it('非 11 位原样返回', () => {
    expect(maskPhone('123')).toBe('123')
  })
})

describe('isValidPhone', () => {
  it('11 位 1 开头为真', () => {
    expect(isValidPhone('13812346543')).toBe(true)
    expect(isValidPhone('2381234654')).toBe(false)
    expect(isValidPhone('138123465')).toBe(false)
  })
})

describe('validatePatient', () => {
  it('缺姓名报错', () => {
    expect(validatePatient({ name: '', phone: '13812346543' }).ok).toBe(false)
  })
  it('手机号非法报错', () => {
    expect(validatePatient({ name: '张三', phone: '123' }).ok).toBe(false)
  })
  it('合法通过', () => {
    expect(validatePatient({ name: '张三', phone: '13812346543' }).ok).toBe(true)
  })
})

describe('searchPatients', () => {
  const list = [
    { seq: 427, name: '张建国', phone: '13812346543' },
    { seq: 408, name: '张建国', phone: '15912342071' },
    { seq: 426, name: '王秀兰', phone: '13612348890' }
  ]
  it('空关键字返回全部', () => {
    expect(searchPatients(list, '').length).toBe(3)
  })
  it('按姓名命中同名两条', () => {
    expect(searchPatients(list, '张建国').length).toBe(2)
  })
  it('按手机号区分同名', () => {
    const r = searchPatients(list, '1591234')
    expect(r.length).toBe(1)
    expect(r[0].seq).toBe(408)
  })
  it('按编号命中', () => {
    expect(searchPatients(list, '#00426')[0].name).toBe('王秀兰')
    expect(searchPatients(list, '427')[0].name).toBe('张建国')
  })
})
