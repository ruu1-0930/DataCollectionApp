<template>
    <base-chart :option="option" @emitChart="val => (echarts = val)" />
</template>

<script setup>
import { ref, watchEffect } from 'vue';

const option = ref({});
const echarts = ref(null);

const props = defineProps({
    xData: {
        type: Array,
        required: true,
    },
    yData: {
        type: Array,
        required: true,
    },
    name: {
        type: String,
        required: true,
    },
});

watchEffect(() => {
    if (echarts.value) {
        option.value = getOption(props.xData, props.yData);
    }
});

const getOption = (xData, yData) => {
    return {
        tooltip: {
            trigger: 'axis',
        },
        grid: {
            top: '5%',
            left: '8%',
            right: '5%',
            bottom: '10%',
        },
        dataZoom: [
            {
                type: 'inside',
                show: true, // x轴是否启用
                filterMode: 'filter',
                start: 95, // 从哪里开始显示
                end: 100, // 到哪里结束显示
                handleSize: 6,
                xAxisIndex: 0, //表示y轴折叠
            },
        ],
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
        series: [
            {
                name: props.name,
                type: 'line',
                symbol: 'circle', // 默认是空心圆（中间是白色的），改成实心圆
                showAllSymbol: true,
                symbolSize: 4,
                smooth: true,
                lineStyle: {
                    normal: {
                        width: 1,
                        color: '#17C3DD', // 线条颜色
                    },
                },
                itemStyle: {
                    color: '#17C3DD',
                    borderColor: '#17C3DD',
                    borderWidth: 2,
                },
                tooltip: {
                    show: true,
                },
                areaStyle: {
                    //区域填充样式
                    normal: {
                        //线性渐变，前4个参数分别是x0,y0,x2,y2(范围0~1);相当于图形包围盒中的百分比。如果最后一个参数是‘true’，则该四个值是绝对像素位置。
                        color: new echarts.value.graphic.LinearGradient(
                            0,
                            0,
                            0,
                            1,
                            [
                                {
                                    offset: 0,
                                    color: 'rgba(25,163,223,.5)',
                                },
                                {
                                    offset: 1,
                                    color: 'rgba(25,163,223, 0.2)',
                                },
                            ],
                            false
                        ),
                    },
                },
                data: yData,
            },
        ],
    };
};
</script>
