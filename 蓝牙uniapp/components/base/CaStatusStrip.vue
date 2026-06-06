<template>
  <view class="ca-strip">
    <view class="ca-dot" />
    <view class="ca-txt">
      <view class="ca-t1l">{{ title }}</view>
      <view class="ca-t2l">{{ sub }}</view>
    </view>
  </view>
</template>

<script setup>
defineProps({ title: String, sub: String })
</script>

<style lang="scss" scoped>
.ca-strip { @include ca-font; display: flex; align-items: center; gap: 18rpx; background: #fdf2e2; border: 1rpx solid #f3dcb4; border-radius: 24rpx; padding: 22rpx 26rpx; margin-bottom: 28rpx; }
.ca-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: $ca-warning; animation: caPulse 1.1s infinite; }
@keyframes caPulse { 50% { opacity: .25; } }
.ca-t1l { font-size: 26rpx; font-weight: 600; color: #a96a12; }
.ca-t2l { font-size: 22rpx; color: #b5853a; }
</style>
