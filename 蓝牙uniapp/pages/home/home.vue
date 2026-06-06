<template>
  <view class="container">
    <!-- 足部示意（固定点位） -->
    <view class="foot-card">
      <view class="foot-bg"></view>
      <!-- 左脚点位 -->
      <view v-for="(p, idx) in pointsPercent.left" :key="'l' + idx" class="dot" :style="{ left: p.x + '%', top: p.y + '%' }" />
      <!-- 右脚点位（镜像） -->
      <view v-for="(p, idx) in rightPoints" :key="'r' + idx" class="dot" :style="{ left: p.x + '%', top: p.y + '%' }" />
    </view>

    <!-- 列表数据 -->
    <view class="section">
      <view class="section-title">左右脚实时参数</view>
      <view class="row">
        <view class="col">
          <view class="col-title">右脚：</view>
          <view class="line">步速：{{ rt.right.speed }}</view>
          <view class="line">步长：{{ rt.right.length }}</view>
          <view class="line">单支撑时间：{{ rt.right.single }}</view>
          <view class="line">双支撑时间：{{ rt.right.double }}</view>
        </view>
        <view class="col">
          <view class="col-title">左脚：</view>
          <view class="line">步速：{{ rt.left.speed }}</view>
          <view class="line">步长：{{ rt.left.length }}</view>
          <view class="line">单支撑时间：{{ rt.left.single }}</view>
          <view class="line">双支撑时间：{{ rt.left.double }}</view>
        </view>
      </view>
      <view class="divider" />
      <view class="avg">
        <view class="line">平均步速：{{ rt.avg.speed }}</view>
        <view class="line">平均步长：{{ rt.avg.length }}</view>
        <view class="line">平均右脚单支撑时长：{{ rt.avg.rightSingle }}</view>
        <view class="line">平均左脚单支撑时长：{{ rt.avg.leftSingle }}</view>
        <view class="line">平均双支撑时长：{{ rt.avg.double }}</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { reactive, computed } from 'vue'

// 点位（百分比坐标）
const pointsPercent = reactive({
  left: [
    { x: 37, y: 8 },
    { x: 22, y: 28 },
    { x: 37, y: 32 },
    { x: 29, y: 30 },
    { x: 18, y: 45 },
    { x: 34, y: 52 },
    { x: 34, y: 64 },
    { x: 29, y: 86 },
    { x: 29, y: 78 }
  ]
})

// 右脚镜像
const rightPoints = computed(() => pointsPercent.left.map((p) => ({ x: Number((100 - p.x).toFixed(1)), y: p.y })))

// 实时与平均参数占位（后续可接入接口数据）
const rt = reactive({
  right: { speed: '-', length: '-', single: '-', double: '-' },
  left: { speed: '-', length: '-', single: '-', double: '-' },
  avg: { speed: '-', length: '-', rightSingle: '-', leftSingle: '-', double: '-' }
})
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
  width: 22rpx;
  height: 22rpx;
  border-radius: 50%;
  background: #60a5fa;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 10rpx rgba(96, 165, 250, 0.2);
}

.dot::after,
.dot::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: rgba(96, 165, 250, 0.35);
  transform: translate(-50%, -50%) scale(1);
  animation: ripple 2.2s ease-out infinite;
}
.dot::before {
  animation-delay: 1.1s;
}

@keyframes ripple {
  0% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.6;
  }
  70% {
    transform: translate(-50%, -50%) scale(2.6);
    opacity: 0;
  }
  100% {
    opacity: 0;
  }
}

/* 参数区样式 */
.section {
  margin-top: 24rpx;
  padding: 24rpx;
  background-color: #fff;
  border-radius: 12rpx;
}
.section-title {
  font-size: 32rpx;
  font-weight: 600;
  position: relative;
  padding-left: 22rpx;
  margin-bottom: 12rpx;
}
.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10rpx;
  width: 12rpx;
  height: 32rpx;
  background: #409eff;
  border-radius: 4rpx;
}
.row {
  display: flex;
  gap: 40rpx;
}
.col {
  flex: 1;
}
.col-title {
  font-weight: 700;
  font-size: 28rpx;
  margin-bottom: 8rpx;
}
.line {
  color: #555;
  margin: 8rpx 0;
}
.divider {
  height: 1rpx;
  background: #e2e1e1;
  margin: 24rpx 0 16rpx;
}
.avg {
  padding-left: 8rpx;
}
</style>
