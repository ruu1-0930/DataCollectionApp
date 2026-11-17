<template>
  <view class="registration-card">
    <view class="title">采集登记</view>
    <view v-if="!patientId" class="note">请先选择患者</view>
    <template v-else>
      <CaInput v-for="field in fields" :key="field.key" :label="field.label" :type="field.type || 'text'"
        :required="field.key !== 'phone'" :model-value="form[field.key] ?? ''" :disabled="disabled || busy"
        @update:modelValue="patch(field.key, $event)" />
      <picker :range="genders" :value="Math.max(0, genders.indexOf(form.gender))" :disabled="disabled || busy" @change="patch('gender', genders[Number($event.detail.value)])">
        <view class="choice">性别 *：{{ form.gender || '请选择' }} ▾</view>
      </picker>
      <picker :range="testTypes" range-key="label" :value="Math.max(0, testTypes.findIndex(t => t.code === form.test_type))" :disabled="disabled || busy" @change="patch('test_type', testTypes[Number($event.detail.value)].code)">
        <view class="choice">测试类型 *：{{ testTypes.find(t => t.code === form.test_type)?.label || '请选择' }} ▾</view>
      </picker>
      <view class="note">备注（选填，最多 2000 字）</view>
      <textarea :value="form.remarks || ''" :maxlength="2000" :disabled="disabled || busy" class="remarks" @input="patch('remarks', $event.detail.value)" />
      <view class="note">{{ disabled ? '采集中，登记只读' : saved ? '已保存，可以开始' : '修改后请重新保存登记' }}</view>
      <view v-for="conflict in conflicts" :key="conflict.field" class="conflict">
        <view>{{ fieldLabel(conflict.field) }}在服务端也有修改</view>
        <view>本地：{{ form[conflict.field] ?? '未填写' }} · 服务端：{{ conflict.serverValue ?? '未填写' }}</view>
        <view class="conflict-actions">
          <button size="mini" :disabled="disabled || busy" @tap="$emit('resolve', { field: conflict.field, keepLocal: false })">使用服务端值</button>
          <button size="mini" :disabled="disabled || busy" @tap="$emit('resolve', { field: conflict.field, keepLocal: true })">保留本地值</button>
        </view>
      </view>
      <view v-if="error" class="error">{{ error }}</view>
      <button :disabled="disabled || busy || conflicts.length > 0" class="save" @tap="$emit('save')">{{ busy ? '处理中…' : '保存登记' }}</button>
    </template>
  </view>
</template>
<script setup>
import { COLLECTION_TEST_TYPES } from '@/utils/collectionRegistration'
const props = defineProps({ patientId: Number, form: { type: Object, default: () => ({}) },
  conflicts: { type: Array, default: () => [] }, disabled: Boolean, busy: Boolean, saved: Boolean, error: String })
const emit = defineEmits(['edit', 'save', 'resolve'])
const testTypes = COLLECTION_TEST_TYPES, genders = ['男', '女']
const fields = [{ key: 'name', label: '姓名' }, { key: 'phone', label: '手机号（选填）', type: 'number' },
  { key: 'age', label: '年龄（0–150 岁）', type: 'number' }, { key: 'height_cm', label: '身高（厘米）', type: 'digit' },
  { key: 'weight_kg', label: '体重（千克）', type: 'digit' }, { key: 'shoe_size_eu', label: '欧码鞋码（支持半码）', type: 'digit' }]
const fieldLabel = field => field === 'gender' ? '性别' : fields.find(item => item.key === field)?.label
function patch(key, value) { if (!props.disabled && !props.busy) emit('edit', { [key]: value }) }
</script>
<style lang="scss" scoped>
.registration-card { @include ca-font; padding: 24rpx; margin-bottom: 24rpx; background: #fff; border-radius: 12rpx; }
.title { font-size: 28rpx; font-weight: 700; margin-bottom: 20rpx; }
.choice { padding: 20rpx 0; font-size: 26rpx; }
.note { color: $ca-t2; font-size: 22rpx; line-height: 1.7; margin: 12rpx 0; }
.remarks { box-sizing: border-box; width: 100%; height: 160rpx; border: 1rpx solid $ca-border; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; }
.error { color: $ca-danger; font-size: 24rpx; margin: 12rpx 0; }
.conflict { border: 1rpx solid $ca-border; border-radius: 12rpx; padding: 16rpx; margin: 12rpx 0; font-size: 24rpx; line-height: 1.6; }
.conflict-actions { display: flex; gap: 12rpx; margin-top: 12rpx; }
.save { background: $ca-primary; color: #fff; font-size: 26rpx; }
</style>
