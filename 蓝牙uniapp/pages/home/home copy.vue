<template>
  <view class="container">
    <!-- 为每个设备显示图表 -->
    <view v-for="device in blueToothStore.deviceList" :key="device.id" class="device-chart-section">
      <uni-section class="chart-section" :title="`${device.device_name} - Single-Double Support`" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
        <view class="chart-container">
          <view class="chart-item">
            <qiun-data-charts :key="`${device.id}-1`" type="arcbar" :opts="getDeviceOptsFirst(device)" :chartData="getDeviceChartDataFirst(device)" />
          </view>
          <view class="chart-item chart-item-right">
            <qiun-data-charts :key="`${device.id}-2`" type="arcbar" :opts="getDeviceOptsSecond(device)" :chartData="getDeviceChartDataSecond(device)" />
          </view>
        </view>
      </uni-section>
    </view>
    <uni-section class="chart-section" title="Left-Right Pressure" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="bar-chart-container">
        <qiun-data-charts type="column" :canvas2d="true" canvasId="pWCGpEDrwDzugNcRluWprKtNzoOpQdvL" :ontouch="true" :opts="optsBar" :chartData="chartDataBar" />
      </view>
    </uni-section>

    <uni-section class="params-section" title="Key Parameters" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="params-container">
        <view
          v-for="(item, index) in state.list"
          :key="item.id"
          :class="{
            'param-item': true,
            'param-item-border': index != state.list.length - 1
          }"
        >
          <text class="param-name">{{ item.name }}</text>
          <text class="param-value">{{ item.value }}</text>
        </view>
      </view>
    </uni-section>
  </view>
</template>

<script setup>
import { reactive, ref, computed, watch } from 'vue'
import { getRingOpts, getBarOpts } from '@/utils/ucharts'
import { getDeviceLatestT1T2Api, getDeviceDailyAveragesApi } from '@/api'
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import { useUserStoreWithOut } from '@/store/modules/user'
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'

const userStore = useUserStoreWithOut()
const blueToothStore = useBlueToothStoreWithOut()

const state = reactive({
  list: [
    {
      name: 'Stride Length',
      value: '1.2m'
    },
    {
      name: 'Walking Speed',
      value: '1.2m/s'
    },
    {
      name: 'Acceleration',
      value: '1.2m/s'
    }
  ],
  // 存储每个设备的数据
  deviceData: {},
  // 每日左右脚压力均值
  dailyDates: [],
  dailyLeft: [],
  dailyRight: []
})

// 归一化到[0,1]，并为0提供极小值避免不渲染
const normalizeArcValue = (value) => {
  const num = Number(value) || 0
  const ratio = num > 1 ? num / 100 : num
  // uCharts arcbar 在0时可能不绘制，给一个极小值以显示空环
  return Math.max(0.000001, Math.min(1, ratio))
}

// 百分比显示（0-100）
const formatPercent = (value) => {
  const num = Number(value) || 0
  return (num > 1 ? num : num * 100).toFixed(2)
}

// 监听设备列表变化，加载所有设备数据
watch(
  () => blueToothStore.deviceList,
  (devices) => {
    if (devices && devices.length > 0) {
      loadAllDeviceData()
    }
  },
  { immediate: true, deep: true }
)

// 加载所有设备数据
const loadAllDeviceData = async () => {
  try {
    let allAnalysisData = await getDeviceDailyAveragesApi()
    allAnalysisData = allAnalysisData.reverse()
    console.log('所有分析数据:', allAnalysisData)
    if (Array.isArray(allAnalysisData)) {
      state.dailyDates = allAnalysisData.map((i) => i.date)
      state.dailyLeft = allAnalysisData.map((i) => Number(i.lp_average) || 0)
      state.dailyRight = allAnalysisData.map((i) => Number(i.rp_average) || 0)
      // 更新柱状图数据
      chartDataBar.value = {
        categories: state.dailyDates,
        series: [
          { name: '左脚压力', textColor: '#FFFFFF', data: state.dailyLeft, color: '#1890FF' },
          { name: '右脚压力', textColor: '#FFFFFF', data: state.dailyRight, color: '#91CB74' }
        ]
      }
    }

    const res = await getDeviceLatestT1T2Api()
    console.log('所有设备数据:', res)

    if (Array.isArray(res)) {
      // 将数据按设备ID分组
      res.forEach((item) => {
        if (item.device_id) {
          state.deviceData[item.device_id] = {
            latest_T1: item.latest_T1 || 0,
            latest_T2: item.latest_T2 || 0
          }
        }
      })
    }
  } catch (error) {
    console.error('加载设备数据失败:', error)
    // 为所有设备设置默认值
    blueToothStore.deviceList.forEach((device) => {
      state.deviceData[device.id] = {
        latest_T1: 0,
        latest_T2: 0
      }
    })
  }
}

// 获取设备的单腿支撑图表配置
const getDeviceOptsFirst = (device) => {
  const data = state.deviceData[device.id] || { latest_T1: 0 }
  return getRingOpts({
    title: {
      name: `${formatPercent(data.latest_T1)}%`,
      fontSize: 20,
      color: '#2fc25b'
    },
    subtitle: {
      name: 'Single',
      fontSize: 14,
      offsetX: 10,
      color: '#2fc25b'
    }
  })
}

// 获取设备的双腿支撑图表配置
const getDeviceOptsSecond = (device) => {
  const data = state.deviceData[device.id] || { latest_T2: 0 }
  return getRingOpts({
    title: {
      name: `${formatPercent(data.latest_T2)}%`,
      fontSize: 20,
      color: '#EE6666'
    },
    subtitle: {
      name: 'Double',
      offsetX: 10,
      fontSize: 14,
      color: '#EE6666'
    }
  })
}

// 获取设备的单腿支撑图表数据
const getDeviceChartDataFirst = (device) => {
  const data = state.deviceData[device.id] || { latest_T1: 0 }
  return {
    series: [
      {
        name: '正确率',
        color: '#2fc25b',
        data: normalizeArcValue(data.latest_T1),
        labelShow: false
      }
    ]
  }
}

// 获取设备的双腿支撑图表数据
const getDeviceChartDataSecond = (device) => {
  const data = state.deviceData[device.id] || { latest_T2: 0 }
  return {
    series: [
      {
        name: '正确率',
        color: '#EE6666',
        data: normalizeArcValue(data.latest_T2),
        labelShow: false
      }
    ]
  }
}

// 页面显示时刷新设备列表与所有设备数据，确保首次进入渲染
onShow(async () => {
  try {
    await blueToothStore.getDevicesList()
  } catch (e) {}
  await loadAllDeviceData()
})

// 下拉刷新处理
onPullDownRefresh(async () => {
  console.log('下拉刷新触发')
  try {
    // 重新加载设备列表
    await blueToothStore.getDevicesList()
    // 重新加载所有设备数据
    if (blueToothStore.deviceList.length > 0) {
      await loadAllDeviceData()
    }
    uni.showToast({
      title: '刷新成功',
      icon: 'success',
      duration: 1500
    })
  } catch (error) {
    console.error('刷新失败:', error)
    uni.showToast({
      title: '刷新失败',
      icon: 'error',
      duration: 1500
    })
  } finally {
    // 停止下拉刷新动画
    uni.stopPullDownRefresh()
  }
})

const optsBar = getBarOpts({
  legend: {
    show: true
  },
  enableScroll: true,
  xAxis: {
    disableGrid: true,
    scrollShow: true,
    itemCount: 4
  },
  touchMoveLimit: 24
})

const chartDataBar = ref({
  categories: [],
  series: [
    { name: '左脚压力', textColor: '#FFFFFF', data: [], color: '#1890FF' },
    { name: '右脚压力', textColor: '#FFFFFF', data: [], color: '#91CB74' }
  ]
})
</script>

<style lang="scss" scoped>
.device-chart-section {
  margin-bottom: 20rpx;
}

.chart-section {
  margin-top: 10rpx;
}

.chart-container {
  display: flex;
  padding: 0 40rpx;
  height: 320rpx;
  border: 1rpx solid #f5f7fa;
  border-bottom-style: solid;
}

.chart-item {
  flex: 1;
  overflow: hidden;
  padding: 0 40rpx;
}

.chart-item-right {
  border-left: 1rpx solid #f5f7fa;
  border-left-style: solid;
}

.bar-chart-container {
  display: flex;
  padding: 0 40rpx;
}

.params-section {
  margin: 10rpx 0;
}

.params-container {
  display: flex;
  padding: 30rpx 40rpx;
  flex-direction: column;
}

.param-item {
  flex: 1;
  padding: 30rpx 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-item-border {
  border-bottom: 1rpx solid #f5f7fa;
  border-bottom-style: solid;
}

.param-name {
  font-size: 28rpx;
  font-weight: 600;
}

.param-value {
  font-size: 28rpx;
  font-weight: 500;
  width: 150rpx;
  text-align: left;
}
</style>
