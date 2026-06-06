<template>
  <div class="p-5px w-full h-full overflow-auto flex flex-col gap-5px">
    <!-- 顶部控制区 -->
    <div class="bg-white p-15px flex flex-col gap-24px">
      <div class="flex items-center gap-24px">
        <div class="flex items-center gap-8px">
          <span>设备选择</span>
          <el-select v-model="panel.currentDevice" style="width: 200px">
            <el-option v-for="d in panel.deviceOptions" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
        </div>
      </div>
      <div class="flex items-center gap-24px">
        <div class="flex items-center gap-8px">
          <span>压力传感器：</span>
          <el-select v-model="panel.pressureEnabled" style="width: 120px">
            <el-option label="关" :value="false" />
            <el-option label="开" :value="true" />
          </el-select>
        </div>
        <div class="flex items-center gap-8px">
          <span>加速度传感器：</span>
          <el-select v-model="panel.accEnabled" style="width: 120px">
            <el-option label="关" :value="false" />
            <el-option label="开" :value="true" />
          </el-select>
        </div>
        <div class="flex items-center gap-15px">
          <div>
            状态：<span :class="panel.online ? 'text-green-600' : 'text-red-500'">{{ panel.online ? '在线' : '离线' }}</span>
          </div>
          <div>采样频率：<u>xx</u></div>
          <div>用户 ID：{{ panel.userId }}</div>
        </div>
      </div>
    </div>

    <!-- 实时压力与说明 -->
    <div class="bg-white p-15px flex-1 overflow-auto">
      <div class="section-title">左右脚实时压力</div>
      <div class="grid grid-cols-2 gap-20px">
        <!-- 足部示意 -->
        <div class="foot-card card relative" ref="footRef">
          <div class="foot-bg"></div>
          <!-- 左脚点位 -->
          <div v-for="(p, idx) in pointsPercent.left" :key="'l' + idx" class="dot" :style="{ left: p.x + '%', top: p.y + '%' }" @mousedown="startDrag('left', idx, $event)" />
          <!-- 右脚点位 -->
          <div v-for="(p, idx) in rightPoints" :key="'r' + idx" class="dot" :style="{ left: p.x + '%', top: p.y + '%' }" @mousedown="startDrag('right', idx, $event)" />
        </div>

        <!-- 说明列表 -->
        <div class="card p-15px text-14px leading-8">
          <div class="grid grid-cols-2 gap-x-24px">
            <div>
              - ax: 左脚加速度 x 轴分量<br />
              - ay: 左脚加速度 y 轴分量<br />
              - az: 左脚加速度 z 轴分量<br />
              - gx: 左脚角速度 x 轴分量<br />
              - gy: 左脚角速度 y 轴分量<br />
              - gz: 左脚角速度 z 轴分量
            </div>
            <div>
              - right_ax: 右脚加速度 x 轴分量<br />
              - right_ay: 右脚加速度 y 轴分量<br />
              - right_az: 右脚加速度 z 轴分量<br />
              - right_gx: 右脚角速度 x 轴分量<br />
              - right_gy: 右脚角速度 y 轴分量<br />
              - right_gz: 右脚角速度 z 轴分量
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, onBeforeUnmount, computed } from 'vue'

// 顶部面板假数据
const panel = reactive({
  deviceOptions: [
    { label: 'ID 01', value: 'ID 01' },
    { label: 'ID 02', value: 'ID 02' },
    { label: 'ID 03', value: 'ID 03' }
  ],
  currentDevice: 'ID 01',
  online: true,
  userId: 'xxx',
  pressureEnabled: true,
  accEnabled: true
})

// 以百分比控制的点位（适配背景图尺寸变化）
const pointsPercent = reactive({
  left: [
    { x: 40, y: 8 },
    { x: 25, y: 28 },
    { x: 40, y: 32 },
    { x: 32, y: 30 },
    { x: 24, y: 45 },
    { x: 37, y: 52 },
    { x: 37, y: 64 },
    { x: 34, y: 86 },
    { x: 34, y: 78 }
  ]
})

const rightPoints = computed(() => pointsPercent.left.map(p => ({ x: Number((100 - p.x).toFixed(1)), y: p.y })))

// 拖拽微调：按住点直接拖动，实时更新百分比坐标
const footRef = ref(null)
let dragging = null // { side: 'left'|'right', idx: number }

function startDrag(side, idx, e) {
  dragging = { side, idx }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', endDrag)
}

function onDrag(e) {
  if (!dragging || !footRef.value) return
  const rect = footRef.value.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * 100
  const y = ((e.clientY - rect.top) / rect.height) * 100
  const clamped = (v) => Math.max(0, Math.min(100, Number(v.toFixed(1))))
  if (dragging.side === 'left') {
    const p = { x: clamped(x), y: clamped(y) }
    pointsPercent.left[dragging.idx] = p
  } else {
    const p = { x: clamped(100 - x), y: clamped(y) }
    pointsPercent.left[dragging.idx] = p
  }
}

function endDrag() {
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', endDrag)
  dragging = null
}

onBeforeUnmount(() => endDrag())
</script>

<style scoped lang="scss">
::v-deep(.el-form-item) {
  margin-bottom: 0 !important;
  margin-right: 0 !important;
}
.section-title {
  font-size: 16px;
  margin-bottom: 12px;
  position: relative;
  padding-left: 14px;
}
.section-title:before {
  content: '';
  position: absolute;
  left: 0;
  top: 3px;
  width: 6px;
  height: 16px;
  background: #409eff;
  border-radius: 2px;
}
.card {
  border: 1px solid #edf0f5;
  border-radius: 8px;
}
.foot-card {
  min-height: 320px;
}
.foot-bg {
  position: relative;
  width: 100%;
  height: 300px;
  background: url('@/assets/images/foot.png') center/contain no-repeat;
}
.dot {
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #60a5fa;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
}

/* 扩散光圈动效 */
.dot::after,
.dot::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: rgba(96, 165, 250, 0.35);
  transform: translate(-50%, -50%) scale(1);
  animation: ripple 2.2s ease-out infinite;
}
.dot::before {
  animation-delay: 1.1s;
}

@keyframes ripple {
  0% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.6;
  }
  70% {
    transform: translate(-50%, -50%) scale(2.6);
    opacity: 0;
  }
  100% {
    opacity: 0;
  }
}
</style>
