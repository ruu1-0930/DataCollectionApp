<template>
  <view class="page">
    <CaInput label="姓名" icon="👤" required placeholder="患者姓名" v-model="f.name" />
    <CaInput label="手机号" icon="📞" required type="number" placeholder="必填 · 同名患者靠它区分" v-model="f.phone" />
    <view class="row2">
      <view class="col">
        <view class="lab">性别</view>
        <view class="seg">
          <view :class="['seg-i', f.gender==='男'&&'on']" @tap="f.gender='男'">男</view>
          <view :class="['seg-i', f.gender==='女'&&'on']" @tap="f.gender='女'">女</view>
        </view>
      </view>
      <view class="col">
        <CaInput label="年龄" type="number" placeholder="岁" v-model="f.age" />
      </view>
    </view>
    <view class="lab">患者编号</view>
    <view class="idrow"><text class="idtag">创建后由系统自动派发</text><text class="idnote">导出科研只用此编号</text></view>
    <view class="btn" @tap="onCreate">创建并设为当前患者</view>
    <view class="hint">姓名仅本机供医护辨认；对外导出默认去标识化，只带编号。</view>
  </view>
</template>

<script setup>
import { reactive } from 'vue'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { validatePatient } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const f = reactive({ name: '', phone: '', gender: '', age: '' })
async function onCreate() {
  const v = validatePatient(f)
  if (!v.ok) return uni.showToast({ title: v.msg, icon: 'none' })
  uni.showLoading({ title: '创建中', mask: true })
  try {
    const p = await ps.create({ ...f })
    uni.hideLoading()
    if (p.existed) uni.showToast({ title: '该患者已存在，已为你选中', icon: 'none', duration: 2000 })
    uni.switchTab({ url: '/pages/home/home' })
  } catch (e) {
    uni.hideLoading()
    uni.showToast({ title: '创建失败：请检查网络', icon: 'none' })
  }
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
.idnote { font-size: 22rpx; color: $ca-t3; }
.btn { margin-top: 40rpx; background: $ca-primary; color: #fff; font-size: 30rpx; font-weight: 700; text-align: center; padding: 28rpx; border-radius: 26rpx; }
.hint { font-size: 22rpx; color: $ca-t3; text-align: center; margin-top: 24rpx; line-height: 1.6; }
</style>
