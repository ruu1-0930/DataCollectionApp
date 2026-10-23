import { defineStore } from 'pinia'
import { store } from '@/store'
import { createRadarNative } from '@/utils/radarNative'
import { createRadarDiscovery } from '@/utils/radarDiscovery'
import { createRadarLink } from '@/utils/radarLink'
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
const runtimes = new WeakMap()
const preferenceKey = 'radar_auto_connect_v1'
const cacheKey = 'radar_verified_ip_v1'
export const useRadarStore = defineStore('radarStore', {
  state: () => ({ autoConnect: uni.getStorageSync(preferenceKey) !== false, foreground: true, entered: false, contextAllowed: true,
    connection: { status: 'idle', candidates: [] }, realtime: null }),
  actions: {
    ensure() {
      if (runtimes.has(this)) return runtimes.get(this)
      const adapter = createRadarNative()
      const discovery = createRadarDiscovery({ adapter,
        cache: { get: token => { const value = uni.getStorageSync(cacheKey); return value?.networkToken === token ? value.ip : null },
          set: (networkToken, ip) => { try { uni.setStorageSync(cacheKey, { networkToken, ip }) } catch { /* Cache is optional; capture persistence is separate. */ } } },
      })
      const link = createRadarLink({ adapter, discovery,
        captureContext: () => useBlueToothStoreWithOut().radarCaptureToken(),
        onState: value => { this.connection = { ...value, candidates: value.candidates || [] }; if (value.status !== 'connected') this.realtime = null },
        onFrame: (payload, receivedAt, epoch, networkToken, token) => {
          if (!this.foreground || !this.contextAllowed) return
          this.realtime = { payload, receivedAt, epoch, networkToken }
          useBlueToothStoreWithOut().acceptRadar(payload, receivedAt, epoch, networkToken, token)
        },
      })
      const runtime = { link }; runtimes.set(this, runtime); return runtime
    },
    open() {
      const op = useOperatorStoreWithOut()
      if (!op.unlocked) return Promise.resolve()
      this.entered = true; this.contextAllowed = true
      const runtime = this.ensure(); runtime.link.setForeground(this.foreground)
      return this.autoConnect ? runtime.link.enable() : Promise.resolve()
    },
    setAuto(value) {
      this.autoConnect = !!value
      try { uni.setStorageSync(preferenceKey, this.autoConnect) } catch { /* Connection preference is optional. */ }
      if (!value) this.disconnect()
      else return this.open()
    },
    connect(ip) {
      const op = useOperatorStoreWithOut()
      if (!op.unlocked || !this.foreground) return Promise.resolve()
      this.entered = true; this.contextAllowed = true
      const runtime = this.ensure(); runtime.link.setForeground(true)
      return runtime.link.connect(ip)
    },
    disconnect() {
      this.autoConnect = false
      try { uni.setStorageSync(preferenceKey, false) } catch { /* Explicit disconnect still takes effect in memory. */ }
      runtimes.get(this)?.link.disconnect(); this.realtime = null
    },
    invalidateCapture() { runtimes.get(this)?.link.invalidateCapture() },
    suspendContext() { this.contextAllowed = false; runtimes.get(this)?.link.setForeground(false); this.realtime = null },
    setForeground(value) {
      this.foreground = !!value
      if (!this.entered) return
      runtimes.get(this)?.link.setForeground(this.foreground && this.contextAllowed && useOperatorStoreWithOut().unlocked)
    },
  },
})
export function useRadarStoreWithOut() { return useRadarStore(store) }
