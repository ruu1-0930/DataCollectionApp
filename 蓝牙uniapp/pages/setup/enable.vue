<template>
  <view class="page">
    <view class="hero">
      <view class="logo">🦶</view>
      <view class="h1">步态采集系统</view>
      <view class="h2">首次启用 · 请填写本机操作信息</view>
    </view>
    <CaInput label="医院" icon="🏥" placeholder="如：市第一人民医院" v-model="f.hospital" />
    <CaInput label="科室" icon="🩺" placeholder="如：康复科" v-model="f.dept" />
    <CaInput label="医生姓名" icon="👤" placeholder="请输入您的姓名" v-model="f.name" />
    <CaInput label="联系方式" icon="📞" type="number" placeholder="手机号" v-model="f.phone" />
    <CaInput label="设置口令" icon="🔒" :password="true" placeholder="自设一个本机口令" v-model="f.passcode" />
    <view class="btn" @tap="onEnable">启用本机</view>
    <view class="hint">仅本机填写一次，之后无需重复登录。\n口令用于打开 App，丢失设备可防数据泄露。</view>
  </view>
</template>

<script setup>
import { reactive } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { isValidPhone } from '@/utils/patient'
const op = useOperatorStoreWithOut()
const f = reactive({ hospital: '', dept: '', name: '', phone: '', passcode: '' })
function onEnable() {
  if (!f.hospital || !f.dept || !f.name) return uni.showToast({ title: '请填写医院/科室/姓名', icon: 'none' })
  if (!isValidPhone(f.phone)) return uni.showToast({ title: '请输入正确手机号', icon: 'none' })
  if (!f.passcode || f.passcode.length < 4) return uni.showToast({ title: '口令至少 4 位', icon: 'none' })
  op.enable({ ...f })
  uni.reLaunch({ url: '/pages/patient/select' })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.hero { text-align: center; padding: 52rpx 0 36rpx; }
.logo { width: 116rpx; height: 116rpx; border-radius: 36rpx; background: $ca-primary-light; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto; }
.h1 { font-size: 38rpx; font-weight: 800; color: $ca-t1; margin-top: 24rpx; }
.h2 { font-size: 25rpx; color: $ca-t2; margin-top: 10rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; white-space: pre-line; }
</style>
