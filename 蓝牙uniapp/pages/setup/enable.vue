<template>
  <view class="page">
    <view class="hero">
      <view class="logo">🦶</view>
      <view class="h1">步态采集系统</view>
      <view class="h2">{{ registering ? '注册新医生账号' : '已有账号登录' }}</view>
    </view>
    <CaInput label="医院" icon="🏥" placeholder="如：市第一人民医院" v-model="f.hospital" />
    <CaInput v-if="registering" label="科室" icon="🩺" placeholder="如：康复科" v-model="f.dept" />
    <CaInput label="医生姓名" icon="👤" placeholder="请输入您的姓名" v-model="f.name" />
    <CaInput label="联系方式" icon="📞" type="number" placeholder="手机号" v-model="f.phone" />
    <CaInput :label="registering ? '设置登录口令' : '登录口令'" icon="🔒" :password="true" placeholder="请输入医生登录口令" v-model="f.passcode" />
    <view class="btn" :class="{ disabled: submitting }" @tap="onEnable">
      {{ submitting ? '提交中…' : (registering ? '注册并启用' : '登录') }}
    </view>
    <button class="switch-mode" :disabled="submitting" @tap="switchMode">{{ registering ? '已有账号？去登录' : '没有账号？注册医生账号' }}</button>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { isValidPhone } from '@/utils/patient'
import { createSubmissionGate, runCommittedSubmission } from '@/utils/submissionGate'
const op = useOperatorStoreWithOut()
const registering = ref(false)
const f = reactive({ hospital: '', dept: '', name: '', phone: '', passcode: '' })
const submitting = ref(false)
const submissionGate = createSubmissionGate((value) => {
  submitting.value = value
})
function switchMode() {
  if (submitting.value) return
  registering.value = !registering.value
  f.passcode = ''
}
async function onEnable() {
  if (!f.hospital.trim() || !f.name.trim()) return uni.showToast({ title: '请填写医院和医生姓名', icon: 'none' })
  if (registering.value && !f.dept.trim()) return uni.showToast({ title: '请填写科室', icon: 'none' })
  if (!isValidPhone(f.phone)) return uni.showToast({ title: '请输入正确手机号', icon: 'none' })
  if (!f.passcode || f.passcode.length < 4) return uni.showToast({ title: '口令至少 4 位', icon: 'none' })
  return runCommittedSubmission({
    gate: submissionGate,
    submit: async () => {
      uni.showLoading({ title: registering.value ? '注册中' : '登录中', mask: true })
      try {
        return registering.value ? await op.enable({ ...f }) : await op.login({ ...f })
      } catch (e) {
        const title = e?.data?.msg || (registering.value ? '注册未完成，请重试' : '登录未完成，请重试')
        uni.showToast({ title, icon: 'none', duration: 2500 })
        return null
      } finally {
        uni.hideLoading()
      }
    },
    onCommitted: () => uni.reLaunch({ url: '/pages/patient/select' }),
  })
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.hero { text-align: center; padding: 52rpx 0 36rpx; }
.logo { width: 116rpx; height: 116rpx; border-radius: 36rpx; background: $ca-primary-light; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto; }
.h1 { font-size: 38rpx; font-weight: 800; color: $ca-t1; margin-top: 24rpx; }
.h2 { font-size: 25rpx; color: $ca-t2; margin-top: 10rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.btn.disabled { opacity: 0.6; pointer-events: none; }
.switch-mode { margin-top: 24rpx; font-size: 26rpx; color: $ca-primary; background: transparent; }
.switch-mode::after { border: none; }
</style>
