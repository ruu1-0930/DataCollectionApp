<template>
  <view class="content">
    <view class="top">
      <!-- 主标题 -->
      <view class="title">
        <text class="font-bold"> Sign Up </text>
      </view>
      <!-- 副标题 -->
      <view class="sub">
        <text
          >已有账号了，<text class="text" @tap="pageTo('/pages/login/login')"
            >马上登录</text
          ></text
        >
      </view>
    </view>
    <view class="middle">
      <form ref="form" @submit="submit()">
        <!-- 用户名 -->
        <view class="flex flex-col">
          <view class="inputStyle">
            <input
              type="text"
              v-model="formData.name"
              maxlength="11"
              placeholder-class="placeholderClass"
              placeholder="用户名"
            />
          </view>
        </view>
        <!-- 性别 -->
        <view class="inputStyle">
          <picker :range="genderOptions" @change="onGenderChange">
            <view class="picker">
              <text v-if="formData.gender">{{ formData.gender }}</text>
              <text v-else class="text-#666">性别</text>
            </view>
          </picker>
        </view>
        <!-- 年龄 -->
        <view class="inputStyle">
          <input
            type="number"
            v-model="formData.age"
            maxlength="2"
            placeholder-class="placeholderClass"
            placeholder="年龄"
          />
        </view>
        <!-- 手机号 -->
        <view class="inputStyle">
          <input
            type="number"
            v-model="formData.phone"
            maxlength="11"
            placeholder-class="placeholderClass"
            placeholder="电话"
            @blur="validatePhone"
          />
        </view>
        <!-- 紧急联系手机号 -->
        <view class="inputStyle">
          <input
            type="number"
            v-model="formData.emergency_phone"
            maxlength="11"
            placeholder-class="placeholderClass"
            placeholder="紧急联系电话"
            @blur="validateeMergencyPhone"
          />
        </view>
        <!-- 邮箱 -->
        <view class="inputStyle">
          <input
            type="email"
            v-model="formData.email"
            placeholder-class="placeholderClass"
            placeholder="邮箱"
            @blur="validateEmail"
          />
        </view>
        <!-- 紧急联系邮箱 -->
        <view class="inputStyle">
          <input
            type="email"
            v-model="formData.emergency_email"
            placeholder-class="placeholderClass"
            placeholder="紧急联系邮箱"
            @blur="validateEmergencyEmail"
          />
        </view>
        <!-- 地址 -->
        <view class="inputStyle">
          <input
            type="text"
            v-model="formData.address"
            placeholder-class="placeholderClass"
            placeholder="地址"
          />
        </view>
        <view class="button">
          <button type="primary" form-type="submit" class="primary common-btn">
            注册
          </button>
        </view>
        <view class="button-text" @tap="pageTo('/pages/login/login')"> 账号登录 </view>
      </form>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive } from "vue";
import { pageTo } from "../../utils/index.js";
import { userRegisterApi } from "@/api";
// 表单
const formData = reactive({
  // 用户名称
  name: "",
  // 性别
  gender: "",
  // 年龄
  age: "",
  // 地址
  address: "",
  // 电话
  phone: "",
  // 邮箱
  email: "",
  // 紧急邮箱
  emergency_email: "",
  // 紧急电话
  emergency_phone: "",
});
//是否正在倒计时
const isCountingDown = ref(false);
//倒计时秒数
const countDown = ref(60);

// 性别选项
const genderOptions = ["男", "女", "其他"];

// 性别选择处理
const onGenderChange = (event) => {
  formData.gender = genderOptions[event.detail.value];
};

// 验证手机号
const validatePhone = () => {
  if (!formData.phone) {
    return true;
  }
  const phonePattern = /^[0-9]{11}$/;
  const phoneError = !phonePattern.test(formData.phone);
  if (phoneError) {
    uni.showToast({
      title: "手机号格式不正确",
      icon: "none",
    });
  }
  return phoneError;
};

// 验证手机号
const validateeMergencyPhone = () => {
  if (!formData.emergency_phone) {
    return true;
  }
  const phonePattern = /^[0-9]{11}$/;
  const phoneError = !phonePattern.test(formData.emergency_phone);
  if (phoneError) {
    uni.showToast({
      title: "手机号格式不正确",
      icon: "none",
    });
  }
  return phoneError;
};

// 验证邮箱
const validateEmail = () => {
  if (!formData.email) {
    return true;
  }
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const emailError = !emailPattern.test(formData.email);
  if (emailError) {
    uni.showToast({
      title: "邮箱格式不正确",
      icon: "none",
    });
  }
  return emailError;
};

const validateEmergencyEmail = () => {
  if (!formData.emergency_email) {
    return true;
  }
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const emailError = !emailPattern.test(formData.emergency_email);
  if (emailError) {
    uni.showToast({
      title: "邮箱格式不正确",
      icon: "none",
    });
  }
  return emailError;
};

//提交表单(注册)
const submit = () => {
  console.log(formData);
  const check = Object.values(formData).every((value) => value);
  if (check) {
    const phone = validatePhone();
    const mergencyPhone = validateeMergencyPhone();
    const email = validateEmail();
    const mergencyEmail = validateEmergencyEmail();

    if (!phone && !mergencyPhone && !email && !mergencyEmail) {
      userRegisterApi(formData).then((res) => {
				uni.showToast({
          title: "注册成功",
          icon: "none",
        });
				pageTo("/pages/login/login");
      });
    }
  } else {
    uni.showToast({
      title: "请完善信填写",
      icon: "none",
    });
  }
};
</script>

<style scoped lang="scss">
.content {
  .top {
    padding-top: 60px;
    padding-left: 20px;
    padding-right: 20px;
    padding-bottom: 50px;

    .title {
      text {
        font-size: 24px;
        font-weight: bold;
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

    .justify-space {
      justify-content: space-between;
      font-size: 14px;
      color: #333;
    }

    .inputStyle {
      display: flex;
      align-items: center;
      margin-bottom: 20px;
      background-color: #f3f5f5;
      padding: 10px 20px;
      font-size: 14px;

      .label {
        padding-right: 10px;
        font-weight: 500;
      }

      .label-left {
        font-weight: 500;
        white-space: nowrap;
        color: #333;
      }

      .placeholderClass {
        color: #666;
        font-size: 12px;
      }

      input {
        width: 100%;

        &::placeholder {
          color: #666;
        }
      }
    }

    .error-text {
      color: red;
      font-size: 12px;
      margin-top: 5px;
      width: 150rpx;
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
