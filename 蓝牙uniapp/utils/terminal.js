// 蓝牙uniapp/utils/terminal.js —— 终端稳定标识（换机/重装视为新终端，可接受）
const TERMINAL_KEY = '__terminal_code__'

// 纯函数：用注入的 rng 生成 v4 形状字符串，便于单测
export function generateTerminalCode(rng = Math.random) {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (rng() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

// uni 包装：首次读不到则生成并持久化
export function getTerminalCode() {
  let code = ''
  try { code = uni.getStorageSync(TERMINAL_KEY) || '' } catch (e) {}
  if (!code) {
    code = generateTerminalCode()
    try { uni.setStorageSync(TERMINAL_KEY, code) } catch (e) {}
  }
  return code
}
