<template>
  <view class="ca-empty">
    <view class="ca-ei">{{ icon }}</view>
    <view class="ca-et">{{ title }}</view>
    <view class="ca-ed"><slot>{{ desc }}</slot></view>
    <view class="ca-eb" v-if="button" @tap="$emit('action')">{{ button }}</view>
  </view>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '📭' },
  title: String, desc: String, button: String
})
defineEmits(['action'])
</script>

<style lang="scss" scoped>
.ca-empty { @include ca-font; text-align: center; padding: 100rpx 48rpx; }
.ca-ei { font-size: 96rpx; opacity: .25; }
.ca-et { font-size: 32rpx; font-weight: 700; color: $ca-t1; margin-top: 28rpx; }
.ca-ed { font-size: 26rpx; color: $ca-t3; margin-top: 16rpx; line-height: 1.6; }
.ca-eb { margin-top: 40rpx; display: inline-block; background: $ca-primary; color: #fff; font-size: 28rpx; font-weight: 600; padding: 24rpx 52rpx; border-radius: 24rpx; }
</style>
