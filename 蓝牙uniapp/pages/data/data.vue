<template>
  <view class="container">
    <CaPatientBar />
    <view class="body">
      <!-- 时间分段 -->
      <view class="seg">
        <view v-for="(t,i) in ranges" :key="i" :class="['seg-i', range===i&&'on']" @tap="range=i">{{ t }}</view>
      </view>

      <block v-if="hasData">
        <!-- KPI 概览 -->
        <view class="kpi">
          <view class="k" v-for="(k,i) in kpis" :key="i">
            <view class="kk">{{ k.label }}</view>
            <view class="kv">{{ k.value }}<text class="ks"> {{ k.unit }}</text></view>
          </view>
        </view>

        <CaCard title="步速趋势">
          <qiun-data-charts type="line" :opts="lineOpts" :chartData="lineData" />
        </CaCard>
        <CaCard title="左右脚压力对比">
          <qiun-data-charts type="column" :opts="barOpts" :chartData="pressureData" />
        </CaCard>
        <CaCard title="单支撑时间（左/右）">
          <qiun-data-charts type="column" :opts="barOpts" :chartData="singleData" />
        </CaCard>
      </block>

      <CaEmpty v-else icon="📊" title="暂无数据" desc="完成一次采集后，这里会显示步态统计与趋势分析" />
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getBarOpts } from '@/utils/ucharts'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { getPatientHistoryApi } from '@/api'
import { mapHistoryItem } from '@/utils/apiShape'

const ps = usePatientStoreWithOut()
const ranges = ['本周', '上周', '本月', '近半年']
const range = ref(0)

const history = ref([])
const hasData = computed(() => history.value.length > 0)

async function loadHistory() {
  const id = ps.currentId
  if (!id) { history.value = []; return }
  try {
    const res = await getPatientHistoryApi(id, { page: 1, page_size: 200 })
    history.value = (res?.items || []).map(mapHistoryItem)
  } catch (e) {
    history.value = [] // 离线/越权：走空态
  }
}
onShow(loadHistory)

// 数值平均：忽略非数值；全空返回 null
const avg = (arr) => {
  const nums = arr.filter((n) => typeof n === 'number' && !Number.isNaN(n))
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null
}
const pad = (n) => (n < 10 ? '0' : '') + n
const fmtTime = (ms) => { const d = new Date(ms); return `${pad(d.getHours())}:${pad(d.getMinutes())}` }

// 分段时间窗口 [start, end)（毫秒），相对当前时刻
function rangeBounds(idx) {
  const now = Date.now()
  const sod = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x.getTime() }
  const sow = (d) => { const x = new Date(sod(d)); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x.getTime() }
  const weekStart = sow(now)
  if (idx === 0) return [weekStart, now]                                 // 本周
  if (idx === 1) return [weekStart - 7 * 864e5, weekStart]               // 上周
  if (idx === 2) { const x = new Date(now); return [new Date(x.getFullYear(), x.getMonth(), 1).getTime(), now] } // 本月
  const half = new Date(now); half.setMonth(half.getMonth() - 6); return [half.getTime(), now] // 近半年
}

// 当前分段内的帧（每帧拆为 L/R 两行）
const framesInRange = computed(() => {
  const [s, e] = rangeBounds(range.value)
  return history.value.filter((h) => h.collectedAt != null && h.collectedAt >= s && h.collectedAt < e)
})

// KPI：分段内全部帧（左右合并）的均值；无数据显示 '-'
const kpis = computed(() => {
  const f = framesInRange.value
  const speed = avg(f.map((x) => x.walkingSpeed))
  const len = avg(f.map((x) => x.stepLength))
  const single = avg(f.map((x) => x.singleSupportTime))
  const double = avg(f.map((x) => x.doubleSupportTime))
  return [
    { label: '平均步速', value: speed == null ? '-' : speed.toFixed(2), unit: 'm/s' },
    { label: '平均步长', value: len == null ? '-' : len.toFixed(1), unit: 'cm' },
    { label: '平均单支撑', value: single == null ? '-' : single.toFixed(2), unit: 's' },
    { label: '平均双支撑', value: double == null ? '-' : double.toFixed(2), unit: 's' }
  ]
})

const lineOpts = { color: ['#2F6DF6'], padding: [10, 10, 0, 10], legend: { show: false },
  xAxis: { disableGrid: true }, yAxis: { gridType: 'dash' },
  extra: { line: { type: 'curve', width: 2 } } }

// 步速趋势：同帧 L/R 共享 collectedAt，按时间分组取左右平均，取最近 20 帧
const lineData = computed(() => {
  const groups = new Map()
  for (const x of framesInRange.value) {
    if (x.collectedAt == null || typeof x.walkingSpeed !== 'number') continue
    if (!groups.has(x.collectedAt)) groups.set(x.collectedAt, [])
    groups.get(x.collectedAt).push(x.walkingSpeed)
  }
  const sorted = [...groups.entries()].sort((a, b) => a[0] - b[0]).slice(-20)
  return {
    categories: sorted.map(([t]) => fmtTime(t)),
    series: [{ name: '步速', data: sorted.map(([, v]) => Number(avg(v).toFixed(2))) }]
  }
})

const barOpts = getBarOpts({ legend: { show: false } })

// 左右脚压力对比：各脚「9 路压力之和」的均值
const pressureData = computed(() => {
  const f = framesInRange.value
  const sum = (p) => (Array.isArray(p) ? p.reduce((a, b) => a + (Number(b) || 0), 0) : 0)
  const L = avg(f.filter((x) => x.foot === 'L').map((x) => sum(x.pressure)))
  const R = avg(f.filter((x) => x.foot === 'R').map((x) => sum(x.pressure)))
  return {
    categories: ['左脚', '右脚'],
    series: [{ name: '平均总压力', data: [L == null ? 0 : Number(L.toFixed(1)), R == null ? 0 : Number(R.toFixed(1))] }]
  }
})

// 单支撑时间：左右脚均值对比
const singleData = computed(() => {
  const f = framesInRange.value
  const L = avg(f.filter((x) => x.foot === 'L').map((x) => x.singleSupportTime))
  const R = avg(f.filter((x) => x.foot === 'R').map((x) => x.singleSupportTime))
  return {
    categories: ['左脚', '右脚'],
    series: [{ name: '单支撑时间', data: [L == null ? 0 : Number(L.toFixed(2)), R == null ? 0 : Number(R.toFixed(2))] }]
  }
})
</script>

<style lang="scss" scoped>
.container { @include ca-font; }
.body { padding: 28rpx 32rpx; }
.seg { display: flex; background: #eef1f5; border-radius: 22rpx; padding: 6rpx; margin-bottom: 28rpx; }
.seg-i { flex: 1; text-align: center; font-size: 25rpx; font-weight: 600; color: $ca-t2; padding: 16rpx; border-radius: 16rpx; }
.seg-i.on { background: #fff; color: $ca-primary; box-shadow: 0 1rpx 3rpx rgba(0,0,0,.08); }
.kpi { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 28rpx; }
.k { background: #fff; border: 1rpx solid $ca-border; border-radius: 28rpx; padding: 26rpx; }
.kk { font-size: 23rpx; color: $ca-t2; }
.kv { font-size: 42rpx; font-weight: 700; color: $ca-t1; margin-top: 6rpx; }
.ks { font-size: 22rpx; color: $ca-t3; }
</style>
