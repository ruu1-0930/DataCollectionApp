<template>
  <view class="content">
    <view class="avatar-container">
      <img class="avatar-image" src="/static/imgs/1.jpg" alt="" srcset="" />
    </view>

    <view class="top">
      <!-- 主标题 -->
      <view class="title">
        <text> Sign In </text>
      </view>
      <view class="sub">
        <text> 还没有账号，<text class="text" @tap="pageTo('/pages/register/register')">立即注册</text> </text>
      </view>
    </view>
    <view class="middle">
      <form ref="form" @submit="submit()">
        <view class="inputStyle">
          <input type="text" v-model="formData.name" maxlength="11" placeholder-class="placeholderClass" placeholder="姓名" />
        </view>
        <view class="inputStyle">
          <input type="number" v-model="formData.identifier" maxlength="11" placeholder-class="placeholderClass" placeholder="电话" />
        </view>
        <view class="button">
          <button type="primary" form-type="submit" class="primary">登录</button>
        </view>
        <view class="button">
          <button type="default" @tap="runNetworkDiagnostic" class="diagnostic-btn">网络诊断</button>
        </view>
        <!-- <view class="button-text"> 忘记密码 </view> -->
      </form>
    </view>
  </view>
</template>

<script setup>
import { reactive } from 'vue'
import { pageTo } from '../../utils/index.js'
import { useUserStoreWithOut } from '@/store'
import { showNetworkDiagnostic } from '@/utils/networkDiagnostic.js'

// 表单
const formData = reactive({
  name: '',
  identifier: ''
})

const userStore = useUserStoreWithOut()

//提交表单(登录)
const submit = async () => {
  if (!formData.name || !formData.identifier) {
    uni.showToast({
      title: '请输入完整信息',
      icon: 'none'
    })
    return
  }

  try {
    const res = await userStore.userLogin(formData)
    if (res) {
      uni.switchTab({
        url: '/pages/home/home'
      })
    }
  } catch (error) {
    console.error('登录失败:', error)
    // 登录失败时提供网络诊断选项
    uni.showModal({
      title: '登录失败',
      content: '网络连接异常，是否进行网络诊断？',
      success: (modalRes) => {
        if (modalRes.confirm) {
          runNetworkDiagnostic()
        }
      }
    })
  }
}

// 网络诊断
const runNetworkDiagnostic = () => {
  showNetworkDiagnostic()
}
</script>

<style scoped lang="scss">
* {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.content {
  .avatar-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 30rpx;
    padding-bottom: 30rpx;
  }

  .avatar-image {
    border-radius: 50%;
    width: 200rpx;
    height: 200rpx;
    margin-top: 150rpx;
    margin-bottom: 100rpx;
  }

  .top {
    padding-top: 20px;
    padding-left: 20px;
    padding-right: 20px;
    padding-bottom: 50px;

    .title {
      text {
        font-size: 24px;
      }
    }

    .sub {
      padding-top: 10px;

      text {
        font-size: 14px;
        color: #999;

        .text {
          color: $uni-color-primary;
        }
      }
    }
  }

  .middle {
    padding: 20px;
    padding-top: 0;

    .inputStyle {
      display: flex;
      align-items: center;
      margin-bottom: 20px;
      background-color: #f3f5f5;
      padding: 12px 20px;
      font-size: 14px;

      .label {
        padding-right: 10px;
        font-weight: 500;
      }

      .placeholderClass {
        color: #bcbcbc;
        font-size: 12px;
      }

      input {
        width: 100%;
      }
    }

    .button {
      margin-top: 30px;
    }

    .primary {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 40px;
      font-size: 14px;
      box-shadow: 3px 5px 10px #eee, 4px 6px 30px #eee;
    }

    .diagnostic-btn {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 40px;
      font-size: 14px;
      margin-top: 10px;
      background-color: #f8f9fa;
      color: #666;
      border: 1px solid #e9ecef;
    }

    .button-text {
      display: flex;
      justify-content: center;
      align-items: center;
      font-size: 14px;
      color: #666;
      margin-top: 20px;
    }
  }

  .bottom {
    display: flex;
    justify-content: center;
    margin-top: 20px;

    .item {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-shrink: 1;
      padding: 5px;
      margin: 20px;
      border-radius: 100px;
      background-color: #939393;

      image {
        width: 30px;
        height: 30px;
      }
    }
  }
}
</style>
