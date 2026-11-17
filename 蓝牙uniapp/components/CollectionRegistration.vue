<template>
  <view class="registration-card">
    <view class="title">采集登记 / Collection registration</view>
    <view v-if="!patientId" class="note">请先选择患者 / Select a patient first</view>
    <template v-else>
      <CaInput v-for="field in fields" :key="field.key" :label="field.label" :type="field.type || 'text'"
        :required="field.key !== 'phone'" :model-value="form[field.key] ?? ''" :disabled="disabled || busy"
        @update:modelValue="patch(field.key, $event)" />
      <picker :range="genders" :value="Math.max(0, genders.indexOf(form.gender))" :disabled="disabled || busy" @change="patch('gender', genders[Number($event.detail.value)])">
        <view class="choice">性别 / Gender *：{{ form.gender || '请选择 / Select' }} ▾</view>
      </picker>
      <picker :range="testTypes" range-key="label" :value="Math.max(0, testTypes.findIndex(t => t.code === form.test_type))" :disabled="disabled || busy" @change="patch('test_type', testTypes[Number($event.detail.value)].code)">
        <view class="choice">测试类型 / Test type *：{{ testTypes.find(t => t.code === form.test_type)?.label || '请选择 / Select' }} ▾</view>
      </picker>
      <view class="note">备注 / Remarks（选填 / Optional，最多 2000 字 / max 2000 characters）</view>
      <textarea :value="form.remarks || ''" :maxlength="2000" :disabled="disabled || busy" class="remarks" @input="patch('remarks', $event.detail.value)" />
      <view class="note">{{ disabled ? '采集中，登记只读 / Read only during capture' : saved ? '已保存，可以开始 / Saved, ready to start' : '请独立保存；修改后需重存 / Save before starting; save again after edits' }}</view>
      <view v-if="error" class="error">{{ error }}</view>
      <button :disabled="disabled || busy" class="save" @tap="$emit('save')">{{ busy ? '处理中 / Working…' : '保存登记 / Save registration' }}</button>
      <view class="note">保存不会开始采集 / Saving does not start capture</view>
    </template>
  </view>
</template>
<script setup>
import { COLLECTION_TEST_TYPES } from '@/utils/collectionRegistration'
const props = defineProps({ patientId: Number, form: { type: Object, default: () => ({}) }, disabled: Boolean, busy: Boolean, saved: Boolean, error: String })
const emit = defineEmits(['edit', 'save'])
const testTypes = COLLECTION_TEST_TYPES, genders = ['男', '女']
const fields = [{ key: 'name', label: '姓名 / Name' }, { key: 'phone', label: '手机号 / Phone（选填 / Optional）', type: 'number' },
  { key: 'age', label: '年龄 / Age (0–150)', type: 'number' }, { key: 'height_cm', label: '身高 / Height (cm)', type: 'digit' },
  { key: 'weight_kg', label: '体重 / Weight (kg)', type: 'digit' }, { key: 'shoe_size_eu', label: 'EU 鞋码 / Shoe size (0.5)', type: 'digit' }]
function patch(key, value) { if (!props.disabled && !props.busy) emit('edit', { [key]: value }) }
</script>
<style lang="scss" scoped>
.registration-card { @include ca-font; padding: 24rpx; margin-bottom: 24rpx; background: #fff; border-radius: 12rpx; }
.title { font-size: 28rpx; font-weight: 700; margin-bottom: 20rpx; }
.choice { padding: 20rpx 0; font-size: 26rpx; }
.note { color: $ca-t2; font-size: 22rpx; line-height: 1.7; margin: 12rpx 0; }
.remarks { box-sizing: border-box; width: 100%; height: 160rpx; border: 1rpx solid $ca-border; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; }
.error { color: $ca-danger; font-size: 24rpx; margin: 12rpx 0; }
.save { background: $ca-primary; color: #fff; font-size: 26rpx; }
</style>
