<template>
  <view class="page">
    <CaInput label="姓名" icon="👤" required placeholder="患者姓名" v-model="f.name" />
    <CaInput label="手机号" icon="📞" type="number" placeholder="选填" v-model="f.phone" />
    <view class="row2">
      <view class="col">
        <view class="lab">性别 *</view>
        <view class="seg">
          <view :class="['seg-i', f.gender==='男'&&'on']" @tap="f.gender='男'">男</view>
          <view :class="['seg-i', f.gender==='女'&&'on']" @tap="f.gender='女'">女</view>
        </view>
      </view>
      <view class="col">
        <CaInput label="年龄" required type="number" placeholder="0–150 岁" v-model="f.age" />
      </view>
    </view>
    <CaInput label="身高（厘米）" required type="digit" v-model="f.height_cm" />
    <CaInput label="体重（千克）" required type="digit" v-model="f.weight_kg" />
    <CaInput label="欧码鞋码" required type="digit" placeholder="支持半码" v-model="f.shoe_size_eu" />
    <view class="lab">患者编号</view>
    <view class="idrow"><text class="idtag">创建后由系统自动分配</text></view>
    <button class="btn" :disabled="saving" @tap="onCreate">创建并设为当前患者</button>
    <view class="hint">手机号选填。请按患者编号选择既有患者。</view>
    <view class="hint">患者资料按账号权限查看。</view>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { normalizePatientProfile } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const op = useOperatorStoreWithOut()
const f = reactive({ name: '', phone: '', gender: '', age: '', height_cm: '', weight_kg: '', shoe_size_eu: '' })
const saving = ref(false)
async function onCreate() {
  if (saving.value) return
  let profile
  try { profile = normalizePatientProfile(f) }
  catch (e) { return uni.showToast({ title: e.message, icon: 'none' }) }
  const clinicianId = op.operator?.clinicianId, authEpoch = op.authRuntime.authEpoch
  const current = () => op.unlocked && op.operator?.clinicianId === clinicianId && op.authRuntime.authEpoch === authEpoch
  saving.value = true
  uni.showLoading({ title: '创建中', mask: true })
  try {
    const p = await ps.create(profile)
    if (!p || !current()) return
    if (p.existed) uni.showToast({ title: '该患者已存在，已为你选中', icon: 'none', duration: 2000 })
    uni.switchTab({ url: '/pages/home/home' })
  } catch (e) {
    if (current()) uni.showToast({ title: '创建失败：请检查网络', icon: 'none' })
  } finally { uni.hideLoading(); saving.value = false }
}
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 40rpx 32rpx; }
.row2 { display: flex; gap: 20rpx; }
.col { flex: 1; }
.lab { font-size: 24rpx; color: $ca-t2; font-weight: 600; margin: 0 4rpx 12rpx; }
.seg { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.seg-i { flex: 1; text-align: center; padding: 22rpx; border-radius: 20rpx; border: 1rpx solid $ca-border; background: #fff; font-size: 26rpx; color: $ca-t2; }
.seg-i.on { border-color: $ca-primary; color: $ca-primary; background: $ca-primary-light; font-weight: 700; }
.idrow { display: flex; align-items: center; gap: 18rpx; }
.idtag { background: #eaf7f0; color: $ca-success; font-size: 22rpx; font-weight: 700; padding: 14rpx 24rpx; border-radius: 18rpx; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; }
</style>
