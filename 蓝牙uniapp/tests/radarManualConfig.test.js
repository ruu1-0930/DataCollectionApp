import { it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { isPrivateIPv4, visibleRadarTargets } from '../utils/radarProtocol'

// Exercise the component's actual setup handlers without a native renderer.
function panel() {
  const radar = { connect: vi.fn(), open: vi.fn(), connection: { status: 'idle' } }
  const source = readFileSync(new URL('../components/RadarPanel.vue', import.meta.url), 'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const state = new Function('ref', 'computed', 'onMounted', 'useRadarStore', 'useBlueToothStore', 'visibleRadarTargets', 'isPrivateIPv4',
    source + `\nreturn { manualIP, manualPopup: typeof manualPopup === 'undefined' ? null : manualPopup,
      manualError: typeof manualError === 'undefined' ? null : manualError,
      openManualConfig: typeof openManualConfig === 'undefined' ? null : openManualConfig,
      closeManualConfig: typeof closeManualConfig === 'undefined' ? null : closeManualConfig,
      connectManual: typeof connectManual === 'undefined' ? null : connectManual };`)(
    value => ({ value }), fn => ({ get value() { return fn() } }), () => {}, () => radar,
    () => ({ collectionState: {} }), visibleRadarTargets, isPrivateIPv4)
  expect(state.openManualConfig).toBeTypeOf('function')
  const popup = { open: vi.fn(), close: vi.fn() }
  state.manualPopup.value = popup
  return { state, radar, popup }
}

it('opens manual configuration and cancels without starting a connection', () => {
  const { state, radar, popup } = panel()
  state.manualIP.value = '192.168.1.20'
  state.manualError.value = 'previous error'
  state.openManualConfig()
  expect(popup.open).toHaveBeenCalledTimes(1)
  expect(state.manualError.value).toBe('')
  state.closeManualConfig()
  expect(popup.close).toHaveBeenCalledTimes(1)
  expect(state.manualIP.value).toBe('192.168.1.20')
  expect(radar.connect).not.toHaveBeenCalled()
})

it.each(['', '8.8.8.8', '192.168.1.999'])('keeps invalid address %j in the dialog without connecting', value => {
  const { state, radar, popup } = panel()
  state.manualIP.value = value
  state.connectManual()
  expect(state.manualError.value).toBeTruthy()
  expect(popup.close).not.toHaveBeenCalled()
  expect(radar.connect).not.toHaveBeenCalled()
})

it('trims a valid private address and delegates once to the existing radar connection', () => {
  const { state, radar, popup } = panel()
  state.manualIP.value = ' 192.168.1.20 '
  state.connectManual()
  expect(state.manualIP.value).toBe('192.168.1.20')
  expect(state.manualError.value).toBe('')
  expect(popup.close).toHaveBeenCalledTimes(1)
  expect(radar.connect).toHaveBeenCalledTimes(1)
  expect(radar.connect).toHaveBeenCalledWith('192.168.1.20')
})
