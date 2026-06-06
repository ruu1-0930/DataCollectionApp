<template>
  <view class="ca-m">
    <view class="ca-mk">{{ label }}</view>
    <view class="ca-mv">{{ value }}<text class="ca-mu" v-if="unit"> {{ unit }}</text></view>
    <view class="ca-mlr" v-if="left !== undefined || right !== undefined">
      <text v-if="left !== undefined">左 <text class="b">{{ left }}</text></text>
      <text v-if="right !== undefined">右 <text class="b">{{ right }}</text></text>
    </view>
  </view>
</template>

<script setup>
defineProps({ label: String, value: [String, Number], unit: String, left: [String, Number], right: [String, Number] })
</script>

<style lang="scss" scoped>
.ca-m { @include ca-font; background: #fff; border: 1rpx solid $ca-border; border-radius: 28rpx; padding: 26rpx; }
.ca-mk { font-size: 23rpx; color: $ca-t2; }
.ca-mv { font-size: 44rpx; font-weight: 700; color: $ca-t1; margin-top: 6rpx; }
.ca-mu { font-size: 22rpx; color: $ca-t3; font-weight: 600; }
.ca-mlr { display: flex; gap: 20rpx; margin-top: 12rpx; font-size: 21rpx; color: $ca-t2; }
.ca-mlr .b { color: $ca-t1; }
</style>
