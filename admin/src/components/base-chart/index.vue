<template>
    <div class="w-100% h-100%" ref="chart"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, markRaw } from 'vue';
import * as echarts from 'echarts';
import 'echarts-liquidfill';

const props = defineProps({
    option: {
        type: Object,
        default: () => ({}),
    },
});

const emit = defineEmits(['chartClick', 'emitChart', 'myChart']);

const chart = ref(null);
const chartInstance = ref(null);

watch(
    () => props.option,
    () => {
        update();
    },
    { deep: true }
);

function chartClick(data) {
    emit('chartClick', data);
}

function initChart() {
    chartInstance.value = markRaw(echarts.init(chart.value));
    emit('myChart', chartInstance.value);

    window.addEventListener('resize', () => {
        resize();
    });

    update();
    addListener();
}

function resize() {
    chartInstance.value.resize();
}

function update() {
    if (chartInstance.value) {
        chartInstance.value.setOption(props.option, true);
    }
}

function addListener() {
    chartInstance.value.on('click', params => {
        chartClick(params);
    });
}

onMounted(() => {
    emit('emitChart', echarts);
    initChart();
});

onBeforeUnmount(() => {
    chartInstance.value.dispose();
    chartInstance.value = null;
    window.removeEventListener('resize', resize);
});
</script>
