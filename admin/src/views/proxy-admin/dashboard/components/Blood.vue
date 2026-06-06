<template>
    <base-chart :option="option" @emitChart="val => (echarts = val)" />
</template>

<script setup>
import { ref, onActivated, onDeactivated } from 'vue';
import { getTodayDataApi } from '@/service/api';

const option = ref({});
const echarts = ref(null);

const timer = ref(null);

onActivated(() => {
    getTodayDataApi({}).then(res => {
        option.value = getOption(res);
    });
    timer.value = setInterval(() => {
        getTodayDataApi({}).then(res => {
            option.value = getOption(res);
        });
    }, 10000);
});

onDeactivated(() => {
    clearInterval(timer.value);
});

const getOption = res => {
    const xData = [],
        seriesData = [];

    ['T1', 'T2', 'T3', 'T4', 'T5'].forEach((item, index) => {
        seriesData.push({
            name: item,
            type: 'line',
            showAllSymbol: false,
            smooth: true,
            lineStyle: {
                normal: {
                    width: 2,
                },
            },
            tooltip: {
                show: true,
            },
            data: [],
        });
    });

    res.forEach(item => {
        xData.push(item.transformed_data.timestamp);
        seriesData[0].data.push(item.transformed_data.T1);
        seriesData[1].data.push(item.transformed_data.T2);
        seriesData[2].data.push(item.transformed_data.T3);
        seriesData[3].data.push(item.transformed_data.T4);
        seriesData[4].data.push(item.transformed_data.T5);
    });

    return {
        tooltip: {
            trigger: 'axis',
        },
        dataZoom: [
            {
                type: 'inside',
                show: true, // x轴是否启用
                filterMode: 'filter',
                start: 99, // 从哪里开始显示
                end: 100, // 到哪里结束显示
                handleSize: 6,
                xAxisIndex: 0, //表示y轴折叠
            },
        ],
        grid: {
            top: '5%',
            left: '8%',
            right: '5%',
            bottom: '10%',
        },
        xAxis: [
            {
                type: 'category',
                boundaryGap: false,
                axisLine: {
                    show: false,
                },
                axisLabel: {
                    show: true,
                },
                splitLine: {
                    show: false,
                },
                axisTick: {
                    show: false,
                },
                data: xData,
            },
        ],
        yAxis: [
            {
                splitLine: {
                    show: true,
                    lineStyle: {
                        color: '#DBDCDD',
                    },
                },
                axisLine: {
                    show: false,
                },
                axisLabel: {
                    show: true,
                },
                axisTick: {
                    show: false,
                },
            },
        ],
        series: seriesData,
    };
};
</script>
