<template>
  <view class="page">
    <view class="hero">
      <view class="logo">🦶</view>
      <view class="h1">步态采集系统</view>
      <view class="h2">{{ subtitle }}</view>
    </view>
    <CaInput label="口令" icon="🔒" :password="true" placeholder="输入口令解锁" v-model="passcode" />
    <view class="btn" @tap="onUnlock">解锁</view>
    <view class="hint">日常打开只需输一次口令。\n非本人？<text class="link" @tap="onReset">重新启用本机</text></view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'
const op = useOperatorStoreWithOut()
const ps = usePatientStoreWithOut()
const passcode = ref('')
const subtitle = computed(() => {
  const o = op.operator || {}
  return [o.hospital, o.dept, o.name].filter(Boolean).join(' · ')
})
function onUnlock() {
  if (!op.unlock(passcode.value)) return uni.showToast({ title: '口令错误', icon: 'none' })
  if (ps.current) uni.switchTab({ url: '/pages/home/home' })
  else uni.reLaunch({ url: '/pages/patient/select' })
}
function onReset() {
  uni.showModal({
    title: '重新启用本机', content: '将清除本机操作员信息，确定？',
    success: (r) => { if (r.confirm) { op.reset(); uni.reLaunch({ url: '/pages/setup/enable' }) } }
  })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.hero { text-align: center; padding: 120rpx 0 36rpx; }
.logo { width: 116rpx; height: 116rpx; border-radius: 36rpx; background: $ca-primary-light; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto; }
.h1 { font-size: 38rpx; font-weight: 800; color: $ca-t1; margin-top: 24rpx; }
.h2 { font-size: 25rpx; color: $ca-t2; margin-top: 10rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; white-space: pre-line; }
.link { color: $ca-primary; }
</style>
