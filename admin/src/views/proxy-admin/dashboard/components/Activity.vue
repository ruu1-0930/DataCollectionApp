<template>
    <base-chart :option="option" @emitChart="val => (echarts = val)" />
</template>

<script setup>
import { ref, onMounted } from 'vue';

const option = ref({});
const echarts = ref(null);

onMounted(() => {
    option.value = getOption();
});

const getOption = () => {
    /**
     *
     * 作者: GhostCat
     * 博客: https://gcat.cc
     * 描述: 双折线图
     *
     */

    let xLabel = ['3.26', '3.27', '3.28', '3.29', '3.30', '3.31'];
    let goToSchool = ['40', '60', '22', '85', '50', '40'];
    let goOutSchool = ['20', '50', '12', '65', '30', '60'];

    return {
        tooltip: {
            trigger: 'axis',
        },

        grid: {
            top: '5%',
            left: '10%',
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
                data: xLabel,
            },
        ],
        yAxis: [
            {
                splitLine: {
                    show: false,
                },
                axisLine: {
                    show: false,
                },
                axisLabel: {
                    show: false,
                },
                axisTick: {
                    show: false,
                },
            },
        ],
        series: [
            {
                type: 'bar',
                barWidth: 20,
                itemStyle: {
                    normal: {
                        color: '#F3C538',
                        barBorderRadius: 24,
                    },
                },
                data: [400, 400, 300, 300, 300, 400, 400, 400, 300],
            },
        ],
    };
};
</script>
