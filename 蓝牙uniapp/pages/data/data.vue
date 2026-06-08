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
            <view :class="['kd', k.up ? 'up':'down']">{{ k.up ? '▲':'▼' }} {{ k.delta }}</view>
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

const kpis = computed(() => ([
  { label: '平均步数', value: '6,820', unit: '步', up: true, delta: '8% 较上周' },
  { label: '平均步速', value: '1.24', unit: 'm/s', up: true, delta: '3%' },
  { label: '平均步长', value: '66', unit: 'cm', up: false, delta: '2%' },
  { label: '双支撑时长', value: '0.19', unit: 's', up: true, delta: '1%' }
]))

const lineOpts = { color: ['#2F6DF6'], padding: [10, 10, 0, 10], legend: { show: false },
  xAxis: { disableGrid: true }, yAxis: { gridType: 'dash' },
  extra: { line: { type: 'curve', width: 2 } } }
const lineData = ref({
  categories: ['一', '二', '三', '四', '五', '六', '日'],
  series: [{ name: '步速', data: [1.1, 1.18, 1.15, 1.27, 1.22, 1.33, 1.3] }]
})

const barOpts = getBarOpts({ legend: { show: true } })
const pressureData = ref({
  categories: ['本周', '上周', '本月', '半年'],
  series: [
    { name: '左', data: [70, 58, 50, 80], color: '#2F6DF6' },
    { name: '右', data: [64, 62, 46, 74], color: '#15A05A' }
  ]
})
const singleData = ref({
  categories: ['本周', '上周', '本月'],
  series: [
    { name: '左', data: [0.6, 0.52, 0.44], color: '#2F6DF6' },
    { name: '右', data: [0.55, 0.5, 0.48], color: '#15A05A' }
  ]
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
.kd { font-size: 22rpx; margin-top: 8rpx; font-weight: 600; }
.kd.up { color: $ca-success; }
.kd.down { color: $ca-danger; }
</style>
