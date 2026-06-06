<template>
  <view class="ca-pb" @tap="onSwitch">
    <view class="ca-av">{{ avatar }}</view>
    <view class="ca-info">
      <view class="ca-nm">{{ name }}</view>
      <view class="ca-id">{{ sub }}</view>
    </view>
    <view class="ca-sw">切换 ⇄</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
const ps = usePatientStoreWithOut()
const name = computed(() => ps.current?.name || '未选择患者')
const avatar = computed(() => (ps.current?.name || '?').slice(0, 1))
const sub = computed(() => {
  const p = ps.current
  if (!p) return '点此选择患者'
  return [ps.currentId, p.gender, p.age ? p.age + '岁' : ''].filter(Boolean).join(' · ')
})
function onSwitch() {
  uni.navigateTo({ url: '/pages/patient/select' })
}
</script>

<style lang="scss" scoped>
.ca-pb { @include ca-font; display: flex; align-items: center; gap: 20rpx; background: #fff; border-bottom: 1rpx solid $ca-border; padding: 20rpx 28rpx; }
.ca-av { width: 68rpx; height: 68rpx; border-radius: 20rpx; background: $ca-primary-light; color: $ca-primary; display: flex; align-items: center; justify-content: center; font-size: 30rpx; font-weight: 700; }
.ca-info { flex: 1; }
.ca-nm { font-size: 28rpx; font-weight: 700; color: $ca-t1; }
.ca-id { font-size: 22rpx; color: $ca-t3; margin-top: 2rpx; }
.ca-sw { font-size: 24rpx; color: $ca-primary; font-weight: 600; }
</style>
