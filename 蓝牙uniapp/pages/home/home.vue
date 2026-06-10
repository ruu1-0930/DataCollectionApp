<template>
  <view class="container">
    <CaPatientBar />
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

    <view class="mh">实时参数</view>
    <view class="mgrid" v-if="hasData">
      <CaMetric label="步速" :value="rt.avg.speed" unit="m/s" :left="rt.left.speed" :right="rt.right.speed" />
      <CaMetric label="步长" :value="rt.avg.length" unit="cm" :left="rt.left.length" :right="rt.right.length" />
      <CaMetric label="单支撑时间" :value="rt.avg.leftSingle" unit="s" :left="rt.left.single" :right="rt.right.single" />
      <CaMetric label="双支撑时间" :value="rt.avg.double" unit="s" :left="rt.left.double" :right="rt.right.double" />
    </view>
    <CaEmpty v-else icon="👣" title="还没有开始采集" desc="连接鞋垫并开始采集后，这里会实时显示步态参数" />
  </view>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useBlueToothStore } from '@/store/modules/blueTooth'
import { shade, mToCm } from '@/utils/footMetrics'

const ble = useBlueToothStore()

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
</script>

<style lang="scss" scoped>
.container {
  padding: 24rpx;
}

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
</style>
