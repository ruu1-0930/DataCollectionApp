<template>
  <view class="container">
    <CaPatientBar />
    <view class="capture-card">
      <view class="capture-title">{{ capture.active ? (capture.waiting ? '采集中 · 等待重新连接' : '正在同步记录') : '同步记录鞋垫与 GPS' }}</view>
      <picker v-if="!capture.active" :range="connectedDevices" range-key="name" :value="selectedIndex" @change="selectDevice">
        <view class="capture-device">设备：{{ chosenDevice ? chosenDevice.name : '请在「我的」连接鞋垫' }} {{ connectedDevices.length > 1 ? '▾' : '' }}</view>
      </picker>
      <view v-else class="capture-device">采集设备：{{ capture.active.device_code }}</view>
      <view class="capture-actions">
        <button v-if="!capture.active" class="capture-start" :disabled="!chosenDevice" @tap="ble.startCollection(chosenDevice.code)">开始同步记录</button>
        <button v-else class="capture-stop" @tap="ble.stopCollection()">停止记录</button>
        <button v-if="capture.queue.sessions" class="capture-retry" :disabled="capture.queue.sending" @tap="ble.retryCollectionUpload()">重试上传</button>
      </view>
      <view class="capture-note">{{ queueText }} · 待上传 {{ capture.queue.pending }} / 5000 条</view>
      <view v-if="reasonText" class="capture-warning">{{ reasonText }}</view>
      <view v-if="capture.rejected" class="capture-note">已忽略 {{ capture.rejected }} 条格式异常消息</view>
      <view class="capture-note">采集时保持 App 前台；离开前台会停止记录。未开始时仅显示实时值。</view>
    </view>
    <!-- 足部示意（固定点位） -->
    <view class="foot-card">
      <view class="foot-bg"></view>
      <!-- 左脚点位 -->
      <view v-for="(p, idx) in pointsPercent.left" :key="'l' + idx" class="dot"
        :style="{ left: p.x + '%', top: p.y + '%', background: leftColors[idx] }">{{ leftVals[idx] }}</view>
      <!-- 右脚点位（镜像） -->
      <view v-for="(p, idx) in rightPoints" :key="'r' + idx" class="dot"
        :style="{ left: p.x + '%', top: p.y + '%', background: rightColors[idx] }">{{ rightVals[idx] }}</view>
    </view>

    <view class="imu-card">
      <view class="imu-head" @tap="imuOpen = !imuOpen">
        <text>IMU 原始数据</text>
        <text class="imu-arrow">{{ imuOpen ? '▾' : '▸' }}</text>
      </view>
      <view v-if="imuOpen" class="imu-body">
        <view class="imu-col">
          <view class="imu-foot">左脚</view>
          <view class="imu-row">加速度 ax {{ imu.left.ax }} · ay {{ imu.left.ay }} · az {{ imu.left.az }}</view>
          <view class="imu-row">角速度 gx {{ imu.left.gx }} · gy {{ imu.left.gy }} · gz {{ imu.left.gz }}</view>
        </view>
        <view class="imu-col">
          <view class="imu-foot">右脚</view>
          <view class="imu-row">加速度 ax {{ imu.right.ax }} · ay {{ imu.right.ay }} · az {{ imu.right.az }}</view>
          <view class="imu-row">角速度 gx {{ imu.right.gx }} · gy {{ imu.right.gy }} · gz {{ imu.right.gz }}</view>
        </view>
      </view>
    </view>

    <view class="mh">实时参数</view>
    <view v-if="ble.realtime.deviceCode" class="source-note">鞋垫实时来源：{{ ble.realtime.deviceCode }}</view>
    <view class="mgrid" v-if="hasData">
      <CaMetric label="步速" :value="rt.avg.speed" unit="m/s" :left="rt.left.speed" :right="rt.right.speed" />
      <CaMetric label="步长" :value="rt.avg.length" unit="cm" :left="rt.left.length" :right="rt.right.length" />
      <CaMetric label="单支撑时间" :value="rt.avg.leftSingle" unit="s" :left="rt.left.single" :right="rt.right.single" />
      <CaMetric label="双支撑时间" :value="rt.avg.double" unit="s" :left="rt.left.double" :right="rt.right.double" />
    </view>
    <CaEmpty v-else icon="👣" title="等待鞋垫实时数据" desc="连接鞋垫后显示实时值，点击开始同步记录后才保存" />
    <view class="gps-card">
      <view class="capture-title">鞋垫 GPS 原始状态</view>
      <template v-if="ble.gpsRealtime">
        <view class="capture-note">来源：{{ ble.gpsRealtime.deviceCode }}</view>
        <view class="gps-row">定位标记 {{ ble.gpsRealtime.fix ? '有效' : '无效 / 搜星中' }} · 卫星 {{ ble.gpsRealtime.sats }}</view>
        <view class="gps-row">HDOP {{ rawValue(ble.gpsRealtime.hdop) }} · 数据年龄 {{ ble.gpsRealtime.age }} ms</view>
        <view class="gps-row">GPS 原始速度 {{ rawValue(ble.gpsRealtime.speed) }} m/s</view>
        <view class="capture-note">手机接收 {{ new Date(ble.gpsRealtime.receivedAt).toISOString() }} · GPS UTC {{ ble.gpsRealtime.utc || '—' }}</view>
      </template>
      <view v-else class="capture-note">等待 GPS1 消息；未定位也会记录原始数据。</view>
      <view class="capture-note">GPS 速度与上方左右脚固件步速独立，共同记录窗口不代表硬件对时。</view>
    </view>
  </view>
</template>

<script setup>
import { reactive, computed, ref } from 'vue'
import { useBlueToothStore } from '@/store/modules/blueTooth'
import { shade, mToCm } from '@/utils/footMetrics'

const ble = useBlueToothStore()
const capture = computed(() => ble.collectionState)
const selectedCode = ref('')
const connectedDevices = computed(() => Object.keys(ble.bles_objs)
  .filter(code => ble.bles_objs[code].isConnected)
  .map(code => ({ code, name: ble.deviceList.find(d => d.device_code === code)?.device_name || code })))
const selectedIndex = computed(() => Math.max(0, connectedDevices.value.findIndex(d => d.code === selectedCode.value)))
const chosenDevice = computed(() => connectedDevices.value[selectedIndex.value])
const selectDevice = event => { selectedCode.value = connectedDevices.value[Number(event.detail.value)]?.code || '' }
const rawValue = value => value == null ? '—' : value
const queueText = computed(() => capture.value.queue.sending ? '上传中' : capture.value.queue.error === 'identity'
  ? '请原操作员解锁后重试' : capture.value.queue.error === 'storage' ? '本地缓存读取或写入失败，请保留数据联系维护'
    : capture.value.queue.paused ? '上传已暂停，数据保留，请检查网络或联系维护后重试' : '本地记录保留，按接收顺序上传')
const reasonText = computed(() => ({ background: '已离开前台，记录已停止；待上传数据已保留。',
  clock_rollback: '手机时间回退，已在最后有效接收时刻停止，请校准时间。',
  capacity: '缓存达到上限，已停止记录；上传后可开始新记录。', storage: '缓存不可用，已停止记录，请保留数据联系维护。',
  patient: '患者已切换，上一位患者的记录已停止。', identity: '操作员身份已变更，原记录已停止并保留。',
  disconnect: '设备已主动断开，记录已停止。', bluetooth_off: '蓝牙已关闭，记录已停止。', delete: '设备已移除，记录已停止。',
}[capture.value.reason] || ''))

// 点位（百分比坐标），下标 = 压力传感器编号 p1..p9（对应足底点位图 1–9）
// p1 脚趾 / p2 前掌内 / p3 前掌中 / p4 前掌外 / p5 足弓外 / p6 足弓内 / p7 中段 / p8 足跟上 / p9 足跟下
const pointsPercent = reactive({
  left: [
    { x: 37, y: 8 },
    { x: 37, y: 32 },
    { x: 29, y: 30 },
    { x: 22, y: 28 },
    { x: 34, y: 52 },
    { x: 18, y: 45 },
    { x: 34, y: 64 },
    { x: 29, y: 78 },
    { x: 29, y: 86 }
  ]
})

// 右脚镜像
const rightPoints = computed(() => pointsPercent.left.map((p) => ({ x: Number((100 - p.x).toFixed(1)), y: p.y })))

// 压力数值（整数）：无实时帧时显示空字符串，避免满屏 0
const leftVals = computed(() =>
  ble.realtime.hasData ? ble.realtime.left.pressure.map((v) => Math.round(Number(v) || 0)) : pointsPercent.left.map(() => ''))
const rightVals = computed(() =>
  ble.realtime.hasData ? ble.realtime.right.pressure.map((v) => Math.round(Number(v) || 0)) : pointsPercent.left.map(() => ''))
// 热力颜色（固定满量程 4093）
const leftColors = computed(() => ble.realtime.left.pressure.map(shade))
const rightColors = computed(() => ble.realtime.right.pressure.map(shade))

// 显示用：数值保留两位；非数值/缺失显示 '-'
const fmt = (v) => {
  const n = Number(v)
  return v === '-' || v == null || Number.isNaN(n) ? '-' : n.toFixed(2)
}
// 左右平均：任一非数值则返回 '-'
const mean = (a, b) => {
  const x = Number(a), y = Number(b)
  return Number.isNaN(x) || Number.isNaN(y) ? '-' : ((x + y) / 2).toFixed(2)
}

// 实时与平均参数：来自蓝牙 store 的最近一帧（采集时每 ~5s 刷新）
const rt = computed(() => {
  const r = ble.realtime
  return {
    left: { speed: fmt(r.left.speed), length: fmt(mToCm(r.left.length)), single: fmt(r.left.single), double: fmt(r.left.double) },
    right: { speed: fmt(r.right.speed), length: fmt(mToCm(r.right.length)), single: fmt(r.right.single), double: fmt(r.right.double) },
    avg: {
      speed: mean(r.left.speed, r.right.speed),
      length: mean(mToCm(r.left.length), mToCm(r.right.length)),
      leftSingle: mean(r.left.single, r.right.single),
      double: mean(r.left.double, r.right.double)
    }
  }
})

// 收到过实时帧才显示参数，否则走空态
const hasData = computed(() => ble.realtime.hasData)

// IMU 折叠卡开关（默认折叠）
const imuOpen = ref(false)
// IMU 显示值：2 位小数；非数值显示 '-'
const imu = computed(() => {
  const f = (o) => ({
    ax: fmt(o.ax), ay: fmt(o.ay), az: fmt(o.az),
    gx: fmt(o.gx), gy: fmt(o.gy), gz: fmt(o.gz)
  })
  return { left: f(ble.realtime.left.imu), right: f(ble.realtime.right.imu) }
})
</script>

<style lang="scss" scoped>
.container {
  padding: 24rpx;
}
.capture-card, .gps-card { @include ca-font; background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 24rpx; }
.gps-card { margin-top: 24rpx; }
.capture-title { font-size: 28rpx; font-weight: 700; color: $ca-t1; margin-bottom: 14rpx; }
.capture-device, .gps-row { font-size: 24rpx; color: $ca-t1; line-height: 1.8; overflow-wrap: anywhere; }
.capture-actions { display: flex; flex-wrap: wrap; gap: 16rpx; margin: 20rpx 0; }
.capture-actions button { margin: 0; font-size: 26rpx; padding: 0 24rpx; border-radius: 12rpx; }
.capture-start { background: $ca-primary; color: #fff; }
.capture-stop { background: $ca-danger; color: #fff; }
.capture-retry { background: $ca-primary-light; color: $ca-primary; }
.capture-note, .source-note { color: $ca-t2; font-size: 22rpx; line-height: 1.7; overflow-wrap: anywhere; }
.source-note { margin-bottom: 16rpx; }
.capture-warning { color: $ca-danger; font-size: 24rpx; line-height: 1.7; margin: 12rpx 0; }

.foot-card {
  position: relative;
  width: 100%;
  min-height: 600rpx;
  background-color: #fff;
  border-radius: 12rpx;
}

.foot-bg {
  width: 100%;
  height: 560rpx;
  background: url('/static/imgs/foot.png') center/contain no-repeat;
}

.dot {
  position: absolute;
  width: 34rpx;
  height: 34rpx;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16rpx;
  font-weight: 700;
  color: #fff;
  /* 1px 白描边保证浅色背景上也看得清 */
  text-shadow: 0 0 2rpx rgba(0, 0, 0, 0.55);
  box-shadow: 0 0 0 4rpx rgba(96, 165, 250, 0.18);
}

.mh { @include ca-font; font-size: 30rpx; font-weight: 700; color: $ca-t1; margin: 24rpx 4rpx 20rpx; }
.mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; }
.imu-card { background: #fff; border-radius: 12rpx; margin: 24rpx 0 0; }
.imu-head { @include ca-font; display: flex; justify-content: space-between; align-items: center;
  padding: 22rpx 24rpx; font-size: 28rpx; font-weight: 700; color: $ca-t1; }
.imu-arrow { color: $ca-t3; font-size: 26rpx; }
.imu-body { display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; padding: 0 24rpx 22rpx; }
.imu-col { background: #f7f9fc; border-radius: 10rpx; padding: 16rpx; }
.imu-foot { font-size: 24rpx; font-weight: 700; color: $ca-t2; margin-bottom: 10rpx; }
.imu-row { font-size: 22rpx; color: $ca-t1; line-height: 1.7; }
</style>
