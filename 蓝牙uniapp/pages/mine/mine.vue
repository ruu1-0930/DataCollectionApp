<template>
  <view class="mine-page">
    <view @tap="pageTo('/pages/mine/profile')" v-if="userStore.token" class="user-profile">
      <img class="user-avatar" :src="`${baseURL}/${userStore.user.avatar}`" alt="" srcset="" />
      <view class="user-info">
        <text class="user-name">{{ userStore.user.name }}</text>
        <text class="user-email">{{ userStore.user.email }}</text>
      </view>
      <view @tap="pageTo('/pages/mine/profile')" class="user-profile-btn">修改资料</view>
    </view>

    <view v-else @tap="pageTo('/pages/login/login')" class="login-prompt">
      <button class="login-btn">还未登录，点击去登陆</button>
    </view>

    <view v-if="userStore.token">
      <uni-notice-bar :speed="40" show-icon scrollable :text="getNoticeBarText" />

      <!-- 功能list -->
      <uni-section
        class="chart-section"
        title="功能列表"
        subTitle=""
        type="line"
        titleColor="#333"
        titleFontSize="34rpx"
      >
        <view class="function-list">
          <view class="function-item" @tap="addDevice">
            <view class="function-icon-box">
              <image src="/static/imgs/1751354444527.png" class="function-icon"></image>
            </view>
            <view class="function-text">新增设备</view>
          </view>
        </view>
      </uni-section>

      <!-- 设备card -->
      <uni-section
        class="chart-section"
        title="设备列表"
        subTitle=""
        type="line"
        titleColor="#333"
        titleFontSize="34rpx"
      >
        <!-- 设备列表 -->
        <swiper
          v-if="blueToothStore.deviceList.length"
          class="swiper"
          :circular="false"
          next-margin="100rpx"
          :indicator-dots="false"
          :autoplay="false"
          :interval="100"
          :duration="300"
        >
          <swiper-item v-for="item in blueToothStore.deviceList" :key="item.id">
            <view class="swiper-item">
              <!-- mask -->
              <view
                @click="handleMask(item)"
                v-if="item.id == activeDeviceId"
                class="device-mask"
                style="background-color: rgba(0, 0, 0, 0.6)"
              >
                <view @click.stop="deleteDevice(item)" class="delete-device">
                  <image class="delete-icon" src="../../static/imgs/1746668189565.png"></image>
                  <view class="delete-text">删除设备</view>
                </view>
              </view>

              <view @click="handleMask(item)" class="device-header">
                <image class="device-icon" src="../../static/imgs/wifi2.png"></image>
                <view class="device-content">
                  <view class="device-info">
                    <view class="device-title">
                      <text class="device-name">{{ item.device_name }}</text>
                      <view v-if="getDeviceStatus(item.device_code)" class="status-connected"> 已连接 </view>
                      <view v-else class="status-disconnected"> 未连接 </view>
                    </view>
                    <text class="device-desc">3 Service Advertised</text>
                  </view>
                  <!-- 连接 -->
                  <image
                    v-if="getDeviceStatus(item.device_code)"
                    class="connect-icon"
                    src="../../static/imgs/1746501374311.png"
                    @click.stop="handleConnect('close', item.id)"
                  ></image>

                  <!-- 未连接 -->
                  <image
                    v-else
                    @click.stop="handleConnect('connect', item.id)"
                    class="connect-icon"
                    src="../../static/imgs/1746501374316.png"
                  ></image>
                </view>
              </view>
              <!-- 设备ID -->
              <view class="device-id">{{ item.device_code }}</view>
              <!-- 设备状态 -->
              <view v-if="getDeviceStatus(item.device_code)" class="device-controls">
                <view class="control-item">
                  <view>控制开关:</view>
                  <view class="picker-content" @click="() => showSwitchActionSheet(item)">
                    <view :style="{ color: item.is_enabled ? '#09be4f' : '#f13131' }">
                      {{ item.is_enabled ? '开启' : '关闭' }}
                    </view>
                    <uni-icons type="right" :color="item.is_enabled ? '#09be4f' : '#f13131'" size="16"></uni-icons>
                  </view>
                </view>
                <view class="control-item">
                  <view>频率:</view>
                  <view class="picker-content" @click="() => showHzActionSheet(item)">
                    <view :style="{ color: item.is_enabled ? '#09be4f' : '#f13131' }">{{ pl[item.frequency] }}</view>
                    <uni-icons type="right" :color="item.is_enabled ? '#09be4f' : '#f13131'" size="16"></uni-icons>
                  </view>
                </view>
              </view>
              <!-- 未连接 -->
              <view v-else class="device-controls">
                <view class="control-item">
                  <view>控制开关:</view>
                  <view>--</view>
                </view>
                <view class="control-item">
                  <view>频率:</view>
                  <view>--</view>
                </view>
              </view>
            </view>
          </swiper-item>
        </swiper>
        
        <!-- 空状态占位符 -->
        <view v-else class="empty-device-placeholder">
          <image class="empty-icon" src="../../static/imgs/wifi2.png"></image>
          <view class="empty-text">暂无设备</view>
          <view class="empty-desc">请添加蓝牙设备</view>
        </view>
      </uni-section>

      <view class="menu-section">
        <button type="primary" @tap="logout" style="border-radius: 30rpx">退出登录</button>
        <!-- <button type="primary" @tap="blueToothStore.searchDevice" style="border-radius: 30rpx; margin-top: 20rpx">
          初始化蓝牙
        </button> -->
      </view>
    </view>

    <yfx-tooltip ref="tooltip"></yfx-tooltip>
  </view>
</template>
<script setup>
import { ref, computed } from 'vue'
import { pageTo } from '../../utils/index.js'
import { useUserStoreWithOut, useBlueToothStoreWithOut } from '@/store'
import { baseURL } from '@/config'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'

const userStore = useUserStoreWithOut()
const blueToothStore = useBlueToothStoreWithOut()

const tooltip = ref(null)

const activeDeviceId = ref(null)

const timer = ref(null)

const hz = [
  {
    value: 'Low',
    label: '1HZ'
  },
  {
    value: 'Medium',
    label: '5HZ'
  },
  {
    value: 'High',
    label: '10HZ'
  }
]

const pl = computed(() => {
  const res = hz.reduce((rs, curr) => {
    rs[curr.value] = curr.label
    return rs
  }, {})
  return res
})

const getNoticeBarText = computed(() => {
  return '如若需要连接设备，请点击添加设备，然后扫描设备二维码'
})

onShow(() => {
  if (userStore.token) {
    blueToothStore.getDevicesList()
  }
})

onLoad(() => {
  timer.value = setInterval(() => {
    if (userStore.token) {
      blueToothStore.getDevicesList()
    }
  }, 5000)
})

onUnload(() => {
  clearInterval(timer.value)
})

const getDeviceStatus = (device_code) => {
  const bles_objs = blueToothStore.bles_objs

  return bles_objs?.[device_code]?.isConnected ? true : false
}

const handleMask = (device) => {
  if (device.id == activeDeviceId.value) {
    activeDeviceId.value = null
  } else {
    activeDeviceId.value = device.id
  }
}

const deleteDevice = (item) => {
  uni.vibrateShort()
  // 判断当前设备是否已经链接
  const bles_objs = blueToothStore.bles_objs
  if (bles_objs?.[item.device_code]?.isConnected) {
    tooltip.value.open({
      msg: '提示',
      content: '当前设备已连接，请先断开连接',
      showCancel: false,
      confirm: () => {
        userStore.deleteDevice(item.id)
      }
    })
    return
  }

  tooltip.value.open({
    msg: '提示',
    content: '确定要删除设备吗？',
    showCancel: true,
    confirm: () => {
      userStore.deleteDevice(item.id)
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

const onPickerChange = (event, id) => {
  uni.vibrateShort()
  const selectedIndex = event.detail.value
  blueToothStore.updateDevice(id, {
    is_enabled: selectedIndex === 0 ? false : true
  })

  const device_code = blueToothStore.deviceList.find((item) => item.id == id)?.device_code

  // 设置蓝牙状态
  if (selectedIndex === 0) {
    blueToothStore.sendMassge('0', device_code)
  } else {
    blueToothStore.sendMassge('1', device_code)
  }
}

const onHzPickerChange = (event, id) => {
  uni.vibrateShort()
  const selectedIndex = event.detail.value

  blueToothStore.updateDevice(id, {
    frequency: hz[selectedIndex].value
  })
  const device_code = blueToothStore.deviceList.find((item) => item.id == id)?.device_code
  // 设置采样率
  blueToothStore.sendMassge(hz[selectedIndex].value, device_code)
}

const logout = () => {
  uni.vibrateShort()

  tooltip.value.open({
    msg: '提示',
    content: '确定要退出登录吗？',
    showCancel: true,
    confirm: () => {
      userStore.logout()
    }
  })
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
      // userStore.addDevice('DEVICE = Insole_1;UUID = 18:8B:0E:CC:81:BD' || res.result)
      blueToothStore.addDevice(res.result)
    }
  })
  // #endif
}

const showSwitchActionSheet = (item) => {
  uni.showActionSheet({
    itemList: ['关闭设备', '开启设备'],
    success: (res) => {
      // res.tapIndex: 0为关闭，1为开启
      onPickerChange({ detail: { value: res.tapIndex } }, item.id)
    }
  })
}

const showHzActionSheet = (item) => {
  uni.showActionSheet({
    itemList: hz.map((h) => h.label),
    success: (res) => {
      onHzPickerChange({ detail: { value: res.tapIndex } }, item.id)
    }
  })
}
</script>

<style lang="scss" scoped>
page {
  background-color: #ffffff;
}

.function-list {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20rpx;
  background-color: #ffffff;
}

.function-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background-color: #ffffff;
  border-radius: 10rpx;
  padding: 20rpx;
  .function-icon-box {
    width: 100rpx;
    height: 100rpx;
    background-color: #007bff;
    border-radius: 10rpx;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .function-icon {
    width: 60rpx;
    height: 60rpx;
  }
  .function-text {
    font-size: 24rpx;
    margin-top: 10rpx;
  }
}

.mine-page {
  background-color: #ffffff;
  min-height: 100vh;
}

.user-profile-btn {
  background-color: rgba(0, 0, 0, 0.2);
  color: #fff;
  padding: 10rpx 20rpx;
  border-radius: 10rpx;
  font-size: 24rpx;
  font-weight: 600;
}

.swiper {
  height: 330rpx;
  padding-left: 20rpx;
}

.empty-device-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 330rpx;
  padding: 40rpx 20rpx;
  background-color: #f8f9fa;
  border-radius: 16rpx;
  margin: 0 20rpx;
}

.empty-icon {
  width: 80rpx;
  height: 80rpx;
  opacity: 0.3;
  margin-bottom: 20rpx;
}

.empty-text {
  font-size: 32rpx;
  color: #666;
  margin-bottom: 10rpx;
  font-weight: 500;
}

.empty-desc {
  font-size: 28rpx;
  color: #999;
}
.swiper-item {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  position: relative;
  overflow: hidden;
  height: calc(100% - 20rpx);
  background-color: #f5f5f5;
  margin: 10rpx 10rpx;
  padding: 20rpx;
  border-radius: 20rpx;
}

.user-profile {
  display: flex;
  align-items: center;
  padding: 30rpx 30rpx 30rpx 0;
  background-color: white;
}

.user-avatar {
  width: 150rpx;
  height: 150rpx;
  border-radius: 50%;
  padding: 40rpx;
}

.user-info {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.user-name {
  font-size: 40rpx;
  font-weight: bold;
  color: #333;
}

.user-email {
  font-size: 28rpx;
  font-weight: bold;
  color: #666;
  margin-top: 20rpx;
}

.login-prompt {
  display: flex;
  align-items: center;
  padding: 50rpx 0;
  background-color: white;
  justify-content: center;
}

.login-btn {
  padding: 50rpx 100rpx;
  border-radius: 50rpx;
  background-color: #007bff;
  color: white;
  font-size: 28rpx;
  font-weight: bold;
}

.device-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.6);
  z-index: 100;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.delete-device {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.delete-icon {
  width: 70rpx;
  height: 70rpx;
  margin-bottom: 10rpx;
}

.delete-text {
  color: white;
  font-size: 28rpx;
  font-weight: 600;
}

.device-header {
  display: flex;
  align-items: center;
  gap: 40rpx;
  border-bottom: 1px solid #e8eaec;
  padding: 20rpx 0;
}

.device-icon {
  width: 100rpx;
  height: 100rpx;
  margin-right: 10rpx;
  flex-shrink: 0;
}

.device-content {
  flex: 1;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
}

.device-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
}

.device-title {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.device-name {
  font-size: 32rpx;
  font-weight: 600;
}

.status-connected {
  font-size: 20rpx;
  margin-left: 10rpx;
  background-color: #09be4f;
  border-radius: 10rpx;
  color: white;
  padding: 3rpx 10rpx;
}

.status-disconnected {
  font-size: 20rpx;
  margin-left: 10rpx;
  background-color: #cccccc;
  border-radius: 10rpx;
  color: white;
  padding: 3rpx 10rpx;
}

.device-desc {
  font-size: 24rpx;
  margin-top: 10rpx;
}

.connect-icon {
  width: 50rpx;
  height: 50rpx;
}

.device-id {
  margin: 20rpx 0;
  font-size: 24rpx;
  font-weight: 600;
}

.device-controls {
  display: flex;
  flex-direction: row;
  gap: 20rpx;
  padding-bottom: 10rpx;
  padding-right: 10rpx;
}

.control-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.control-item:first-child {
  width: max-content;
}

.picker-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.menu-section {
  padding: 30rpx;
  display: flex;
  flex-direction: column;
}

.menu-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 30rpx 20rpx;
}

.menu-item-border {
  border-bottom: 1px solid #e8eaec;
}

.menu-text {
  font-size: 28rpx;
  font-weight: 500;
}
</style>
