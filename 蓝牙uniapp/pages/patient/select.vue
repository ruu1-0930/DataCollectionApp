<template>
  <view class="page">
    <view class="srch">
      <text>🔍</text>
      <input class="srch-ipt" placeholder="搜索姓名 / 手机号 / 编号" placeholder-class="srch-ph"
        :value="kw" @input="kw = $event.detail.value" />
    </view>
    <view class="newbtn" @tap="goNew"><text class="plus">＋</text>新建患者</view>

    <view class="pl-h">
      <text class="t">最近采集</text>
      <text class="t muted">共 {{ all.length }} 人</text>
    </view>

    <CaEmpty v-if="list.length === 0" icon="🧑‍⚕️" title="还没有患者"
      desc="点上方「新建患者」录入第一位患者" />

    <view v-for="p in list" :key="p.seq" class="pcell" @tap="onPick(p.seq)">
      <view class="av">{{ p.name.slice(0,1) }}</view>
      <view class="info">
        <view class="nm">{{ p.name }} <text class="ph">{{ mask(p.phone) }}</text></view>
        <view class="meta">{{ id(p.seq) }} · 最近 {{ fmtDate(p.lastAt) }} · {{ p.count || 0 }} 次采集</view>
      </view>
      <text class="arr">›</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { maskPhone, formatSubjectId } from '@/utils/patient'
const ps = usePatientStoreWithOut()
const kw = ref('')
const all = computed(() => ps.patients)
const list = computed(() => ps.list(kw.value))
const mask = maskPhone
const id = formatSubjectId
function fmtDate(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function goNew() { uni.navigateTo({ url: '/pages/patient/new' }) }
function onPick(seq) {
  ps.select(seq)
  uni.switchTab({ url: '/pages/home/home' })
}
onShow(() => { /* 从新建页返回时列表自动随 store 更新 */ })
</script>

<style lang="scss" scoped>
.page { @include ca-font; min-height: 100vh; background: $ca-bg; padding: 28rpx 32rpx; }
.srch { display: flex; align-items: center; gap: 16rpx; background: #eef1f5; border-radius: 22rpx; padding: 20rpx 24rpx; margin-bottom: 24rpx; }
.srch-ipt { flex: 1; font-size: 26rpx; color: $ca-t1; }
.srch-ph { color: $ca-t3; }
.newbtn { display: flex; align-items: center; justify-content: center; gap: 14rpx; border: 3rpx dashed #c7d2e3; color: $ca-primary; font-size: 28rpx; font-weight: 700; border-radius: 26rpx; padding: 26rpx; margin-bottom: 24rpx; background: #fbfcfe; }
.plus { font-size: 34rpx; }
.pl-h { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18rpx; }
.pl-h .t { font-size: 24rpx; color: $ca-t2; font-weight: 600; }
.pl-h .muted { color: $ca-t3; }
.pcell { display: flex; align-items: center; gap: 22rpx; background: #fff; border: 1rpx solid $ca-border; border-radius: 26rpx; padding: 24rpx 26rpx; margin-bottom: 18rpx; }
.pcell .av { width: 76rpx; height: 76rpx; border-radius: 22rpx; background: $ca-primary-light; color: $ca-primary; display: flex; align-items: center; justify-content: center; font-size: 30rpx; font-weight: 700; }
.pcell .info { flex: 1; }
.pcell .nm { font-size: 29rpx; font-weight: 700; color: $ca-t1; }
.pcell .ph { font-size: 22rpx; color: $ca-t3; font-weight: 500; }
.pcell .meta { font-size: 22rpx; color: $ca-t3; margin-top: 4rpx; }
.pcell .arr { color: $ca-t3; font-size: 32rpx; }
</style>
