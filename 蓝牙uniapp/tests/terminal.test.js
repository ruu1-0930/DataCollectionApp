// 蓝牙uniapp/tests/terminal.test.js
import { describe, it, expect } from 'vitest'
import { generateTerminalCode } from '../utils/terminal.js'

describe('generateTerminalCode', () => {
  it('生成 RFC4122 v4 形状字符串', () => {
    const code = generateTerminalCode(() => 0.5)
    expect(code).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
  it('第 3 段首位恒为版本号 4', () => {
    expect(generateTerminalCode(() => 0)[14]).toBe('4')
  })
  it('两次调用注入不同随机源得到不同值', () => {
    let i = 0
    const seq = () => [0.1, 0.9, 0.3, 0.7][(i++) % 4]
    expect(generateTerminalCode(seq)).not.toBe(generateTerminalCode(() => 0.5))
  })
})
