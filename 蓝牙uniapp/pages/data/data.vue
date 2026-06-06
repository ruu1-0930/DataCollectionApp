<template>
  <view class="container">
    <!-- 步数统计（均值） -->
    <uni-section class="chart-section" title="步数统计（均值）" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="chart-row">
        <view class="chart-item">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Current Week', '#2fc25b')" :chartData="arc.currentWeek.steps" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Week', '#EE6666')" :chartData="arc.lastWeek.steps" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Month', '#5c65de')" :chartData="arc.lastMonth.steps" />
        </view>
      </view>
    </uni-section>

    <!-- 步长统计（均值） -->
    <uni-section class="chart-section" title="步长统计（均值）" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="chart-row">
        <view class="chart-item">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Current Week', '#2fc25b')" :chartData="arc.currentWeek.stepLength" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Week', '#EE6666')" :chartData="arc.lastWeek.stepLength" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Month', '#5c65de')" :chartData="arc.lastMonth.stepLength" />
        </view>
      </view>
    </uni-section>

    <!-- 步速统计（均值） -->
    <uni-section class="chart-section" title="步速统计（均值）" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="chart-row">
        <view class="chart-item">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Current Week', '#2fc25b')" :chartData="arc.currentWeek.stepSpeed" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Week', '#EE6666')" :chartData="arc.lastWeek.stepSpeed" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Month', '#5c65de')" :chartData="arc.lastMonth.stepSpeed" />
        </view>
      </view>
    </uni-section>

    <!-- 新增图片里面的内容-->
    <uni-section class="chart-section" title="右左脚压力统计" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="bar-chart-container">
        <qiun-data-charts type="column" :opts="optsBar" :chartData="chartDataBar" />
      </view>
    </uni-section>

    <!-- 右脚单支撑统计（均值） -->
    <uni-section class="chart-section" title="右脚单支撑统计（均值）" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="chart-row">
        <view class="chart-item">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Current Week', '#2fc25b')" :chartData="arc.currentWeek.rightSingle" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Week', '#EE6666')" :chartData="arc.lastWeek.rightSingle" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Month', '#5c65de')" :chartData="arc.lastMonth.rightSingle" />
        </view>
      </view>
    </uni-section>

    <!-- 左脚单支撑统计（均值） -->
    <uni-section class="chart-section" title="左脚单支撑统计（均值）" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
      <view class="chart-row">
        <view class="chart-item">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Current Week', '#2fc25b')" :chartData="arc.currentWeek.leftSingle" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Week', '#EE6666')" :chartData="arc.lastWeek.leftSingle" />
        </view>
        <view class="chart-item chart-item-border">
          <qiun-data-charts type="arcbar" :height="160" :opts="getRing('0.000000', 'Last Month', '#5c65de')" :chartData="arc.lastMonth.leftSingle" />
        </view>
      </view>
    </uni-section>
  </view>
</template>

<script setup>
import { reactive } from 'vue'
import { getRingOpts, getBarOpts } from '@/utils/ucharts'

// 测试数据：使用 0~1 之间的比值；页面展示标题用 6 位小数
const arc = reactive({
  currentWeek: {
    steps: { series: [{ name: '步数', color: '#2fc25b', data: 0.2, labelShow: false }] },
    stepLength: { series: [{ name: '步长', color: '#2fc25b', data: 0.35, labelShow: false }] },
    stepSpeed: { series: [{ name: '步速', color: '#2fc25b', data: 0.12, labelShow: false }] },
    rightSingle: { series: [{ name: '右脚单支撑', color: '#2fc25b', data: 0.18, labelShow: false }] },
    leftSingle: { series: [{ name: '左脚单支撑', color: '#2fc25b', data: 0.22, labelShow: false }] }
  },
  lastWeek: {
    steps: { series: [{ name: '步数', color: '#EE6666', data: 0.18, labelShow: false }] },
    stepLength: { series: [{ name: '步长', color: '#EE6666', data: 0.25, labelShow: false }] },
    stepSpeed: { series: [{ name: '步速', color: '#EE6666', data: 0.08, labelShow: false }] },
    rightSingle: { series: [{ name: '右脚单支撑', color: '#EE6666', data: 0.16, labelShow: false }] },
    leftSingle: { series: [{ name: '左脚单支撑', color: '#EE6666', data: 0.2, labelShow: false }] }
  },
  lastMonth: {
    steps: { series: [{ name: '步数', color: '#5c65de', data: 0.22, labelShow: false }] },
    stepLength: { series: [{ name: '步长', color: '#5c65de', data: 0.28, labelShow: false }] },
    stepSpeed: { series: [{ name: '步速', color: '#5c65de', data: 0.14, labelShow: false }] },
    rightSingle: { series: [{ name: '右脚单支撑', color: '#5c65de', data: 0.12, labelShow: false }] },
    leftSingle: { series: [{ name: '左脚单支撑', color: '#5c65de', data: 0.18, labelShow: false }] }
  }
})

const getRing = (title, subTitle, color) =>
  getRingOpts({
    title: { name: title, fontSize: 18, color },
    subtitle: { name: subTitle, offsetX: 10, fontSize: 11, color }
  })

// 条形图配置与测试数据（参考 data copy.vue）
const optsBar = getBarOpts({
  legend: { show: true }
})

const chartDataBar = reactive({
  categories: ['本周', '上周', '上月', '前3个月', '前6个月'],
  series: [
    { name: '右脚', textColor: '#FFFFFF', data: [35, 33, 31, 13, 34], color: '#1890FF' },
    { name: '左脚', textColor: '#FFFFFF', data: [18, 27, 21, 6, 28], color: '#91CB74' }
  ]
})
</script>

<style lang="scss" scoped>
.container {
  padding: 0rpx 20rpx 40rpx;
}
.chart-section {
  border-radius: 12rpx;
  margin: 16rpx 0 16rpx;
}
.bar-chart-container {
  padding: 0 10rpx 10rpx;
}
.chart-row {
  display: flex;
  flex-direction: row;
  padding: 0 10rpx;
  height: 320rpx;
}
.chart-item {
  flex: 1;
  overflow: hidden;
  padding: 0 10rpx 20rpx;
}
.chart-item-border {
  border-left: 2rpx solid #f5f7fa;
}
</style>
