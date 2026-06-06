<template>
  <div class="p-5px w-full h-full overflow-auto flex flex-col gap-5px">
    <!-- 顶部信息条 -->
    <div class="bg-white p-15px flex items-center flex-wrap gap-20px">
      <div>用户总数：{{ header.totalUsers }}</div>
      <div class="flex items-center gap-8px">
        <span>用户</span>
        <el-select v-model="header.currentUser" placeholder="选择用户" style="width: 200px">
          <el-option v-for="u in header.userOptions" :key="u.value" :label="u.label" :value="u.value" />
        </el-select>
      </div>
      <div>年龄：{{ header.age }}</div>
      <div>性别：{{ header.gender }}</div>
      <div>身高：{{ header.height }}</div>
      <div>体重：{{ header.weight }}</div>
      <div>位置：{{ header.location }}</div>
      <div>设备 ID：{{ header.deviceIds.join('、') }}</div>
    </div>

        <div class="bg-white p-15px flex-1 overflow-auto">
      <!-- 主体两列布局 -->
      <div class="grid grid-cols-2 gap-20px">
        <!-- 左侧：多个环形图分组 -->
        <div class="flex flex-col gap-20px">
                    <div class="section">
            <div class="text-16px mb-8px">步数统计（均值）</div>
                        <div class="grid grid-cols-3 gap-16px">
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">本周</div>
                <div :ref="(el) => (refsMap.stepCount.week = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上周</div>
                <div :ref="(el) => (refsMap.stepCount.lastWeek = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上月</div>
                <div :ref="(el) => (refsMap.stepCount.lastMonth = el)" class="chart-mini"></div>
              </div>
            </div>
          </div>

                    <div class="section">
            <div class="text-16px mb-8px">步长统计（均值）</div>
                        <div class="grid grid-cols-3 gap-16px">
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">本周</div>
                <div :ref="(el) => (refsMap.stepLen.week = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上周</div>
                <div :ref="(el) => (refsMap.stepLen.lastWeek = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上月</div>
                <div :ref="(el) => (refsMap.stepLen.lastMonth = el)" class="chart-mini"></div>
              </div>
            </div>
          </div>

                    <div class="section">
            <div class="text-16px mb-8px">步速统计（均值）</div>
                        <div class="grid grid-cols-3 gap-16px">
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">本周</div>
                <div :ref="(el) => (refsMap.stepSpeed.week = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上周</div>
                <div :ref="(el) => (refsMap.stepSpeed.lastWeek = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上月</div>
                <div :ref="(el) => (refsMap.stepSpeed.lastMonth = el)" class="chart-mini"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧：柱状图 + 两组环形图 -->
        <div class="flex flex-col gap-20px">
                    <div class="section">
            <div class="text-16px mb-8px">左右脚压力统计</div>
                        <div :ref="(el) => (barRefs.pressure = el)" class="chart-bar card"></div>
          </div>
                    <div class="section">
            <div class="text-16px mb-8px">右脚单支撑统计（均值）</div>
            <div class="grid grid-cols-3 gap-16px">
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">本周</div>
                <div :ref="(el) => (refsMap.rightSupport.week = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上周</div>
                <div :ref="(el) => (refsMap.rightSupport.lastWeek = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上月</div>
                <div :ref="(el) => (refsMap.rightSupport.lastMonth = el)" class="chart-mini"></div>
              </div>
            </div>
          </div>
                    <div class="section">
            <div class="text-16px mb-8px">左脚单支撑统计（均值）</div>
            <div class="grid grid-cols-3 gap-16px">
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">本周</div>
                <div :ref="(el) => (refsMap.leftSupport.week = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上周</div>
                <div :ref="(el) => (refsMap.leftSupport.lastWeek = el)" class="chart-mini"></div>
              </div>
                            <div class="mini-item flex flex-col items-center">
                <div class="text-12px mb-6px">上月</div>
                <div :ref="(el) => (refsMap.leftSupport.lastMonth = el)" class="chart-mini"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'

// 顶部信息假数据
const header = reactive({
  totalUsers: 128,
  currentUser: 'ID 001',
  userOptions: [
    { label: 'ID 001', value: 'ID 001' },
    { label: 'ID 002', value: 'ID 002' },
    { label: 'ID 003', value: 'ID 003' }
  ],
  age: 28,
  gender: '男',
  height: '175cm',
  weight: '68kg',
  location: '上海',
  deviceIds: ['DEV-001', 'DEV-002', 'DEV-003']
})

// refs 容器
const refsMap = reactive({
  stepCount: { week: null, lastWeek: null, lastMonth: null },
  stepLen: { week: null, lastWeek: null, lastMonth: null },
  stepSpeed: { week: null, lastWeek: null, lastMonth: null },
  rightSupport: { week: null, lastWeek: null, lastMonth: null },
  leftSupport: { week: null, lastWeek: null, lastMonth: null }
})
const barRefs = reactive({ pressure: null })

// echarts 实例
const chartInstances = []

function createDonut(dom, value, color = '#409EFF') {
  const ins = echarts.init(dom)
  ins.setOption({
    tooltip: { show: false },
    series: [
      {
        type: 'pie',
        radius: ['70%', '90%'],
        avoidLabelOverlap: false,
        label: {
          show: true,
          position: 'center',
          formatter: value.toFixed(6),
          color: '#333',
          fontSize: 12
        },
        labelLine: { show: false },
        data: [
          { value, name: 'value', itemStyle: { color } },
          { value: Math.max(1, 100 - value), name: 'rest', itemStyle: { color: '#e5eaf3' } }
        ]
      }
    ]
  })
  chartInstances.push(ins)
}

function createPressureBar(dom) {
  const ins = echarts.init(dom)
  const months = ['本月', '上月', '前3个月', '前4个月', '前5个月', '前6个月']
  const left = [18, 27, 21, 24, 21, 28]
  const right = [35, 31, 33, 31, 28, 34]
  ins.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['左脚', '右脚'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value' },
    series: [
      { name: '左脚', type: 'bar', data: left, itemStyle: { color: '#73C0DE' }, stack: false },
      { name: '右脚', type: 'bar', data: right, itemStyle: { color: '#5470C6' }, stack: false }
    ]
  })
  chartInstances.push(ins)
}

function initCharts() {
  // 模拟值
  const mk = () => Number((Math.random() * 5).toFixed(6))
  const colors = ['#67C23A', '#E6A23C', '#409EFF']
  // 步数
  createDonut(refsMap.stepCount.week, mk(), colors[0])
  createDonut(refsMap.stepCount.lastWeek, mk(), colors[1])
  createDonut(refsMap.stepCount.lastMonth, mk(), colors[2])
  // 步长
  createDonut(refsMap.stepLen.week, mk(), colors[0])
  createDonut(refsMap.stepLen.lastWeek, mk(), colors[1])
  createDonut(refsMap.stepLen.lastMonth, mk(), colors[2])
  // 步速
  createDonut(refsMap.stepSpeed.week, mk(), colors[0])
  createDonut(refsMap.stepSpeed.lastWeek, mk(), colors[1])
  createDonut(refsMap.stepSpeed.lastMonth, mk(), colors[2])
  // 右脚单支撑
  createDonut(refsMap.rightSupport.week, mk(), colors[0])
  createDonut(refsMap.rightSupport.lastWeek, mk(), colors[1])
  createDonut(refsMap.rightSupport.lastMonth, mk(), colors[2])
  // 左脚单支撑
  createDonut(refsMap.leftSupport.week, mk(), colors[0])
  createDonut(refsMap.leftSupport.lastWeek, mk(), colors[1])
  createDonut(refsMap.leftSupport.lastMonth, mk(), colors[2])

  // 柱状图
  createPressureBar(barRefs.pressure)
}

function resizeAll() {
  chartInstances.forEach((c) => c.resize())
}

onMounted(async () => {
  await nextTick()
  initCharts()
  window.addEventListener('resize', resizeAll)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeAll)
  chartInstances.forEach((c) => c.dispose())
})
</script>

<style scoped lang="scss">
.chart-mini {
  width: 120px;
  height: 120px;
}
.chart-bar {
  width: 100%;
  height: 280px;
}
.section {
    padding-bottom: 12px;
    border-bottom: 1px solid #e5e7eb;
}
.mini-item {
    border: 1px solid #edf0f5;
    border-radius: 8px;
    padding: 8px 0;
}
.card {
    border: 1px solid #edf0f5;
    border-radius: 8px;
}
</style>
