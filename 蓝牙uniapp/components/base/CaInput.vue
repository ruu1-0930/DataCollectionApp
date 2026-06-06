<template>
  <view class="ca-field">
    <view class="ca-label" v-if="label">
      {{ label }}<text v-if="required" class="ca-req"> *</text>
    </view>
    <view class="ca-input">
      <text v-if="icon" class="ca-ic">{{ icon }}</text>
      <input
        class="ca-ipt"
        :type="type"
        :password="password"
        :placeholder="placeholder"
        :value="modelValue"
        placeholder-class="ca-ph"
        @input="$emit('update:modelValue', $event.detail.value)"
      />
    </view>
  </view>
</template>

<script setup>
defineProps({
  label: String, placeholder: String, icon: String,
  modelValue: [String, Number],
  type: { type: String, default: 'text' },
  password: { type: Boolean, default: false },
  required: { type: Boolean, default: false }
})
defineEmits(['update:modelValue'])
</script>

<style lang="scss" scoped>
.ca-field { margin-bottom: 24rpx; }
.ca-label { @include ca-font; font-size: 24rpx; color: $ca-t2; font-weight: 600; margin: 0 4rpx 12rpx; }
.ca-req { color: $ca-danger; }
.ca-input {
  display: flex; align-items: center; gap: 16rpx;
  background: #fff; border: 1rpx solid $ca-border; border-radius: $ca-radius-input;
  padding: 24rpx 26rpx;
}
.ca-ic { font-size: 30rpx; }
.ca-ipt { @include ca-font; flex: 1; font-size: 28rpx; color: $ca-t1; }
.ca-ph { color: $ca-t3; }
</style>
