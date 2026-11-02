<template>
  <view class="radar-panel">
    <view class="radar-title">室内雷达（可选）</view>
    <view class="radar-row"><text>自动发现并连接</text><switch :checked="radar.autoConnect" @change="radar.setAuto($event.detail.value)" /></view>
    <view class="radar-note">{{ statusText }}</view>
    <view v-for="candidate in radar.connection.candidates" :key="candidate.ip" class="radar-row">
      <text>{{ candidate.ip }} · frames {{ candidate.frames }} · {{ candidate.stale ? '陈旧' : '有响应' }}</text>
      <button size="mini" @tap="radar.connect(candidate.ip)">选择</button>
    </view>
    <template v-if="radar.realtime">
      <view class="radar-note">frames {{ radar.realtime.payload.frames }} · age {{ radar.realtime.payload.age_ms ?? '—' }} ms · {{ stale ? '陈旧 / 无有效目标' : '当前观测' }}</view>
      <view v-for="target in targets" :key="target.slot" class="radar-target">槽位 {{ target.slot }} · x {{ target.x_mm / 1000 }} m · y {{ target.y_mm / 1000 }} m · 径向速度 {{ target.speed_cms / 100 }} m/s</view>
    </template>
    <view class="radar-note">{{ capture.active ? (capture.radarReason ? '雷达记录已暂停：' + capture.radarReason : '在共同采集窗口记录') : '连接仅显示；点击上方开始后记录' }} · 雷达待发 {{ capture.queue.radarPending || 0 }} / 5000</view>
    <view v-if="capture.queue.radarPaused" class="radar-note">雷达上传已暂停，待发保留；鞋垫与 GPS 继续。检查网络后点上方重试上传。</view>
    <view class="radar-note">槽位不代表患者身份；径向速度不代表完整步速。手机接收时间并非硬件对时。</view>
    <view class="radar-actions">
      <button size="mini" @tap="openManualConfig">手动配置</button>
      <button size="mini" @tap="radar.disconnect()">断开并暂停自动连接</button>
    </view>
    <uni-popup ref="manualPopup" type="center" :is-mask-click="false">
      <view class="radar-dialog">
        <view class="radar-title">手动连接雷达</view>
        <view class="radar-note">手机需与雷达连接同一 Wi-Fi。请输入雷达的局域网 IPv4 地址。</view>
        <text class="radar-input-label">雷达 IP 地址</text>
        <input v-model="manualIP" class="radar-ip-input" type="text" :maxlength="32" placeholder="例如 192.168.1.20" confirm-type="done" @confirm="connectManual" />
        <view v-if="manualError" class="radar-input-error">{{ manualError }}</view>
        <view class="radar-dialog-actions">
          <button size="mini" @tap="closeManualConfig">取消</button>
          <button size="mini" type="primary" @tap="connectManual">连接</button>
        </view>
      </view>
    </uni-popup>
  </view>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRadarStore } from '@/store/modules/radar'
import { useBlueToothStore } from '@/store/modules/blueTooth'
import { isPrivateIPv4, visibleRadarTargets } from '@/utils/radarProtocol'
const radar = useRadarStore(), ble = useBlueToothStore()
const manualPopup = ref(null), manualIP = ref(''), manualError = ref('')
function openManualConfig() {
  manualError.value = ''
  manualPopup.value.open()
}
function closeManualConfig() { manualPopup.value.close() }
function connectManual() {
  const ip = manualIP.value.trim()
  if (!isPrivateIPv4(ip)) {
    manualError.value = '请输入有效的私网 IPv4 地址，例如 192.168.1.20'
    return
  }
  manualIP.value = ip
  manualError.value = ''
  closeManualConfig()
  radar.connect(ip)
}
const capture = computed(() => ble.collectionState)
const targets = computed(() => visibleRadarTargets(radar.realtime?.payload))
const stale = computed(() => !targets.value.length)
const statusText = computed(() => ({ idle: '尚未连接', discovering: '正在当前 Wi-Fi 查找雷达', selection: '发现多台设备，请选择', connected: '已连接', connecting: '连接中', permission: '本地网络权限未获准，请在系统设置授权后重试；鞋垫和 GPS 可继续', unsupported: '此系统暂不支持雷达；鞋垫和 GPS 可继续', wifi_unavailable: '请连接与雷达相同的 Wi-Fi', not_found: '未发现雷达，请检查硬件 Wi-Fi、网络隔离或手动输入 IP', retry_wait: '等待下一轮发现', protocol: '雷达消息格式异常，请检查设备协议', network: '雷达网络中断，正在退避重试', network_changed: 'Wi-Fi 已变化，重新发现中', background: 'App 离开前台，雷达已暂停', paused: '已主动暂停自动连接', invalid_ip: '仅支持私网 IPv4 地址', discovery_timeout: '发现已超时，请检查网络后重试' }[radar.connection.status] || '雷达暂不可用，请检查网络后重试'))
onMounted(() => radar.open())
</script>
<style scoped>
.radar-panel { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 24rpx; }
.radar-title { font-size: 28rpx; font-weight: 700; margin-bottom: 14rpx; }
.radar-row { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; font-size: 24rpx; }
.radar-note { color: #666; font-size: 22rpx; line-height: 1.7; overflow-wrap: anywhere; margin: 10rpx 0; }
.radar-target { font-size: 24rpx; line-height: 1.8; }
.radar-actions { display: flex; flex-wrap: wrap; gap: 12rpx; }
.radar-dialog { box-sizing: border-box; width: 620rpx; max-width: 88vw; padding: 32rpx; background: #fff; border-radius: 24rpx; }
.radar-input-label { display: block; margin-top: 24rpx; font-size: 24rpx; color: #334155; }
.radar-ip-input { border: 1px solid #cbd5e1; border-radius: 12rpx; padding: 18rpx; margin-top: 12rpx; font-size: 28rpx; }
.radar-input-error { margin-top: 12rpx; color: #b42318; font-size: 24rpx; line-height: 1.5; }
.radar-dialog-actions { display: flex; justify-content: flex-end; gap: 16rpx; margin-top: 24rpx; }
.radar-dialog-actions button { margin: 0; }
button { margin: 12rpx 12rpx 0 0; }
</style>
