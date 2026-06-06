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
                data: xLabel,
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
                type: 'line',
                symbol: 'circle', // 默认是空心圆（中间是白色的），改成实心圆
                showAllSymbol: true,
                symbolSize: 4,
                smooth: true,
                lineStyle: {
                    normal: {
                        width: 1,
                        color: '#9EC675', // 线条颜色
                    },
                },
                itemStyle: {
                    color: '#9EC675',
                    borderColor: '#9EC675',
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
                                    color: 'rgba(158,198,117,.5)',
                                },
                                {
                                    offset: 1,
                                    color: 'rgba(158,198,117, 0.2)',
                                },
                            ],
                            false
                        ),
                    },
                },
                data: goToSchool,
            },
        ],
    };
};
</script>
