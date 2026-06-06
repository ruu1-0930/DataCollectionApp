<template>
    <div class="h-600px overflow-auto">
        <div class="pb-6px">
            <div class="text-14px color-#9D9D9D">商家信息：</div>
            <div class="text-16px font-bold">{{ info.user && info.user.username }}</div>
        </div>
        <div class="flex justify-between font-bold pr-10px">
            <div class="flex-1">{{ productName }}</div>
            <div class="color-#FF4D4F ml-10px">￥{{ info.price }}</div>
        </div>

        <div class="mt-6px">
            <span class="color-#9D9D9D text-14px">{{ info.description }}</span>
            <template v-for="item in defectList" :key="item.key">
                <span class="color-#9D9D9D text-14px ml-4px">{{ item.name }}{{ defectKey[info[item.key]] }}{{ item.name1 }}</span>
            </template>
        </div>
        <div class="grid grid-cols-2 gap-10px mt-10px">
            <div v-for="item in baseList" :key="item.key" class="px-10px py-6px w-100% border border-solid border-#F0F0F0 rounded-4px">
                <div class="text-12px color-#9D9D9D">{{ item.title }}</div>
                <div class="text-14px font-bold" :style="getColor(info[item.key])">{{ info[item.key] || '正常' }}</div>
            </div>
        </div>
        <div class="font-bold py-10px">整体外观</div>
        <div class="grid grid-cols-3 gap-10px">
            <div v-for="(item, i) in overall_appearance_images" :key="i" class="w-100% h-180px">
                <el-image
                    class="w-100% h-100% rounded-8px"
                    hide-on-click-modal
                    :initial-index="i"
                    :src="item"
                    :preview-src-list="overall_appearance_images"
                ></el-image>
            </div>
        </div>
        <div class="font-bold py-10px">瑕疵特写</div>
        <div class="grid grid-cols-3 gap-10px">
            <div v-for="(item, i) in defect_images" :key="i" class="w-100% h-180px">
                <el-image
                    class="w-100% h-100% rounded-8px"
                    hide-on-click-modal
                    :initial-index="i"
                    :src="item"
                    :preview-src-list="defect_images"
                ></el-image>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed } from 'vue';
const baseList = ref([
    {
        title: '屏幕',
        key: 'screen_info',
    },
    {
        title: '前后摄像头',
        key: 'camera_info',
    },
    {
        title: '闪光灯',
        key: 'flash_light',
    },
    {
        title: '电池效率',
        key: 'battery_efficiency',
    },
    {
        title: '指纹/面容识别功能',
        key: 'biometric_auth',
    },
    {
        title: '上下扬声器',
        key: 'speakers',
    },
    {
        title: '光线/距离传感器',
        key: 'sensors',
    },
    {
        title: '麦克风',
        key: 'microphone',
    },
    {
        title: '物理按键',
        key: 'physical_buttons',
    },
    {
        title: '充电接口',
        key: 'charging_port',
    },
    {
        title: 'WiFi/SIM卡/蓝牙信号',
        key: 'connectivity',
    },
    {
        title: '保修时长',
        key: 'warranty_period',
    },
]);
const defectKey = {
    none: '无',
    slight: '轻微',
    obvious: '明显',
};
const defectList = ref([
    {
        name: '屏幕',
        key: 'screen_damage',
        name1: '划痕',
    },
    {
        name: '后盖',
        key: 'back_cover_damage',
        name1: '划痕',
    },
    {
        name: '边框',
        key: 'frame_damage',
        name1: '磕碰',
    },
]);
const attributeList = ref([]);
const productName = computed(() => {
    return props.info.brand_info
        ? `${props.info.brand_info.brand_name} ${props.info.model_info.model_name} ${props.info.storage} ${props.info.version}`
        : '';
});
const overall_appearance_images = computed(() => {
    return props.info.overall_appearance_images && props.info.overall_appearance_images.split(',');
});
const defect_images = computed(() => {
    return props.info.defect_images && props.info.defect_images.split(',');
});

const props = defineProps({
    info: {
        type: Object,
        default: {},
    },
});

const getColor = key => {
    if (!key) return {};
    const obj = attributeList.value.find(item => item.attribute_value === key);
    if (obj && obj.attribute_score == 0) {
        return {
            color: '#FF4D4F',
        };
    } else {
        return {};
    }
};
</script>
