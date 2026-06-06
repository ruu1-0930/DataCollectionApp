<template>
    <div class="h-600px">
        <div class="flex items-center">
            <image :src="info.cpUrl" class="w-60px h-60px rounded-60px"></image>
            <div class="flex-1 ml-14px">
                <div class="font-bold font-16px">{{ info.logisticsCompanyName }}</div>
                <div class="color-#9D9D9D mt-5px">{{ info.mailNo }}</div>
            </div>
        </div>
        <div class="mt-14px h-500px overflow-y-auto">
            <el-timeline style="max-width: 600px">
                <el-timeline-item v-for="(activity, index) in tracesData" :key="index" :type="typeMap[activity.type]" :timestamp="activity.time">
                    {{ activity.desc }}
                </el-timeline-item>
            </el-timeline>
        </div>
    </div>
</template>

<script setup>
import { watch, onMounted, ref } from 'vue';
import { getExpressInfoApi } from '@/service/api';

const info = ref({});
const tracesData = ref([]);

const props = defineProps({
    orderNo: {
        type: String,
        default: '',
    },
});

const typeMap = {
    DELIVERING: 'success',
    ACCEPT: 'info',
    TRANSPORT: 'warning',
    SIGN: 'primary',
};

watch(
    () => props.orderNo,
    val => {
        if (val) {
            getExpressInfo();
        }
    }
);

onMounted(() => {
    getExpressInfo();
});

async function getExpressInfo() {
    if (!props.orderNo) return;
    const res = await getExpressInfoApi({ order_no: props.orderNo });
    info.value = res;
    tracesData.value = res.logisticsTraceDetailList.reverse();
}
</script>

<style lang="scss" scoped>
:deep(.el-form-item) {
    margin-bottom: 0;
}

:deep(.el-table__inner-wrapper:before) {
    background: none;
}
</style>

<style lang="scss">
.el-timeline {
    padding-left: 14px !important;
}
</style>
