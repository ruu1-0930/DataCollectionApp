<template>
  <view class="ca-card">
    <view class="ca-card-h" v-if="title">{{ title }}</view>
    <slot />
  </view>
</template>

<script setup>
defineProps({ title: String })
</script>

<style lang="scss" scoped>
.ca-card {
  background: #fff; border: 1rpx solid $ca-border; border-radius: $ca-radius-card;
  padding: 32rpx; margin-bottom: 28rpx; box-shadow: $ca-shadow-card;
}
.ca-card-h { @include ca-font; font-size: 28rpx; font-weight: 700; color: $ca-t1; margin-bottom: 20rpx; }
</style>
