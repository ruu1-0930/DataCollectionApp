<template>
  <view class="mine-page">
    <!-- 患者上下文 + 采集归属 -->
    <CaPatientBar />
    <view class="attr">本次采集归属：{{ attrText }}</view>

    <!-- 采集中状态（以蓝牙已连接近似） -->
    <CaStatusStrip v-if="isCollecting" title="采集中" :sub="collectSub" />

    <!-- 操作员信息 -->
    <CaCard title="操作员信息">
      <view class="op-row"><text class="op-k">医院</text><text class="op-v">{{ op.operator?.hospital || '—' }}</text></view>
      <view class="op-row"><text class="op-k">科室</text><text class="op-v">{{ op.operator?.dept || '—' }}</text></view>
      <view class="op-row"><text class="op-k">医生</text><text class="op-v">{{ op.operator?.name || '—' }}</text></view>
      <view class="op-row"><text class="op-k">联系方式</text><text class="op-v">{{ op.operator?.phone || '—' }}</text></view>
      <view class="op-btn danger" @tap="reEnable">重新启用本机</view>
    </CaCard>

    <uni-notice-bar :speed="40" show-icon scrollable :text="getNoticeBarText" />

    <!-- 设备列表 -->
    <CaCard title="设备列表">
      <view class="dev-actions">
        <view class="dev-add" @tap="addDevice">+ 新增设备</view>
      </view>

      <view v-if="blueToothStore.deviceList.length" class="dev-list">
        <view v-for="item in blueToothStore.deviceList" :key="item.id" class="dev-card">
          <view class="dev-head">
            <view class="dev-meta">
              <view class="dev-title">
                <text class="dev-name">{{ item.device_name }}</text>
                <text v-if="getDeviceStatus(item.device_code)" class="dev-tag on">已连接</text>
                <text v-else class="dev-tag off">未连接</text>
              </view>
              <text class="dev-code">{{ item.device_code }}</text>
            </view>
          </view>

          <view class="dev-ops">
            <view
              v-if="getDeviceStatus(item.device_code)"
              class="dev-op danger"
              @tap="handleConnect('close', item.id)"
            >
              断开连接
            </view>
            <view v-else class="dev-op primary" @tap="handleConnect('connect', item.id)">连接</view>
            <view class="dev-op danger-o" @tap="deleteDevice(item)">删除</view>
          </view>
        </view>
      </view>

      <!-- 空状态 -->
      <CaEmpty v-else icon="📡" title="暂无设备" desc="点击新增设备扫描二维码添加" />
    </CaCard>

    <yfx-tooltip ref="tooltip"></yfx-tooltip>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useBlueToothStoreWithOut } from '@/store'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'

const blueToothStore = useBlueToothStoreWithOut()
const op = useOperatorStoreWithOut()

const tooltip = ref(null)
const timer = ref(null)

// 采集归属：医院 · 科室 · 医生
const attrText = computed(() => {
  const a = op.attribution()
  return [a.hospital, a.dept, a.doctor].filter(Boolean).join(' · ') || '未设置'
})

// 采集中：用已连接设备近似（无独立采集协议/标志）
const connectedCodes = computed(() =>
  Object.keys(blueToothStore.bles_objs).filter((code) => blueToothStore.bles_objs[code]?.isConnected)
)
const isCollecting = computed(() => connectedCodes.value.length > 0)
const collectSub = computed(() => {
  const names = connectedCodes.value.map((code) => {
    return blueToothStore.deviceList.find((d) => d.device_code === code)?.device_name || code
  })
  return `已连接 ${names.length} 台：${names.join('、')}`
})

const getNoticeBarText = computed(() => {
  return '如若需要连接设备，请点击新增设备，然后扫描设备二维码'
})

onShow(() => {
  blueToothStore.getDevicesList()
})

onLoad(() => {
  timer.value = setInterval(() => {
    blueToothStore.getDevicesList()
  }, 5000)
})

onUnload(() => {
  clearInterval(timer.value)
})

const getDeviceStatus = (device_code) => {
  return blueToothStore.bles_objs?.[device_code]?.isConnected ? true : false
}

const deleteDevice = (item) => {
  uni.vibrateShort()
  // 已连接的设备需先断开再删除
  if (blueToothStore.bles_objs?.[item.device_code]?.isConnected) {
    tooltip.value.open({
      msg: '提示',
      content: '当前设备已连接，请先断开连接',
      showCancel: false,
      confirm: () => {
        blueToothStore.deleteDevice(item.id)
      }
    })
    return
  }

  tooltip.value.open({
    msg: '提示',
    content: '确定要删除设备吗？',
    showCancel: true,
    confirm: () => {
      blueToothStore.deleteDevice(item.id)
    }
  })
}

const handleConnect = (type, id) => {
  if (type == 'close') {
    uni.vibrateShort()
    tooltip.value.open({
      msg: '提示',
      content: '确定要断开连接吗？',
      showCancel: true,
      confirm: () => {
        blueToothStore.disconnectDevice(id)
      }
    })
  }
  if (type == 'connect') {
    uni.vibrateShort()
    tooltip.value.open({
      msg: '提示',
      content: '确定要连接设备吗？',
      showCancel: true,
      confirm: () => {
        blueToothStore.connectDevice(id)
      }
    })
  }
}

const addDevice = () => {
  // #ifdef H5
  uni.showToast({ title: '暂不支持H5端', icon: 'none' })
  // #endif

  // #ifndef H5
  uni.scanCode({
    scanType: 'qrCode',
    autoZoom: true,
    autoDecodeCharset: true,
    success: function (res) {
      console.log('条码：' + res.result)
      blueToothStore.addDevice(res.result)
    }
  })
  // #endif
}

// 重新启用本机：清操作员信息并回到启用页
function reEnable() {
  uni.showModal({
    title: '重新启用本机',
    content: '将清除本机操作员信息并退出，确定？',
    success: (r) => {
      if (r.confirm) {
        op.reset()
        uni.reLaunch({ url: '/pages/setup/enable' })
      }
    }
  })
}
</script>

<style lang="scss" scoped>
page {
  background-color: $ca-bg;
}

.mine-page {
  background-color: $ca-bg;
  min-height: 100vh;
  padding-bottom: 40rpx;
}

.attr {
  @include ca-font;
  font-size: 22rpx;
  color: $ca-t2;
  background: #eaf7f0;
  border-radius: 18rpx;
  padding: 16rpx 22rpx;
  margin: 20rpx;
}

// CaCard 自带左右 margin 之外，包裹时与页面留白对齐
.mine-page :deep(.ca-card) {
  margin-left: 20rpx;
  margin-right: 20rpx;
}

.op-row {
  @include ca-font;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14rpx 0;
  border-bottom: 1rpx solid $ca-border;
}
.op-row:last-of-type {
  border-bottom: none;
}
.op-k {
  font-size: 26rpx;
  color: $ca-t2;
}
.op-v {
  font-size: 26rpx;
  color: $ca-t1;
  font-weight: 600;
}

.op-btn {
  @include ca-font;
  margin-top: 28rpx;
  text-align: center;
  font-size: 28rpx;
  font-weight: 600;
  padding: 22rpx 0;
  border-radius: $ca-radius-input;
}
.op-btn.danger {
  color: $ca-danger;
  background: #fdeced;
}

.dev-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20rpx;
}
.dev-add {
  @include ca-font;
  font-size: 26rpx;
  font-weight: 600;
  color: $ca-primary;
  background: $ca-primary-light;
  padding: 14rpx 28rpx;
  border-radius: $ca-radius-input;
}

.dev-list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.dev-card {
  background: $ca-bg;
  border: 1rpx solid $ca-border;
  border-radius: $ca-radius-input;
  padding: 24rpx;
}

.dev-head {
  display: flex;
  align-items: center;
}
.dev-meta {
  flex: 1;
}
.dev-title {
  display: flex;
  align-items: center;
}
.dev-name {
  @include ca-font;
  font-size: 30rpx;
  font-weight: 700;
  color: $ca-t1;
}
.dev-tag {
  @include ca-font;
  font-size: 20rpx;
  margin-left: 14rpx;
  border-radius: 8rpx;
  color: #fff;
  padding: 3rpx 12rpx;
}
.dev-tag.on {
  background: $ca-success;
}
.dev-tag.off {
  background: $ca-t3;
}
.dev-code {
  @include ca-font;
  display: block;
  margin-top: 10rpx;
  font-size: 24rpx;
  color: $ca-t2;
}

.dev-ops {
  display: flex;
  gap: 20rpx;
  margin-top: 24rpx;
}
.dev-op {
  @include ca-font;
  flex: 1;
  text-align: center;
  font-size: 26rpx;
  font-weight: 600;
  padding: 18rpx 0;
  border-radius: $ca-radius-input;
}
.dev-op.primary {
  color: #fff;
  background: $ca-primary;
}
.dev-op.danger {
  color: #fff;
  background: $ca-danger;
}
.dev-op.danger-o {
  color: $ca-danger;
  background: #fdeced;
}
</style>
