<template>
    <div class="p-5px w-full h-full overflow-hidden flex flex-col gap-5px">
        <Header>
            <el-form :inline="true" class="grid grid-cols-8 gap-16px">
                <el-form-item class="col-span-2">
                    <el-date-picker
                        value-format="YYYY-MM-DD"
                        v-model="state.dateRange"
                        start-placeholder="Start Date"
                        end-placeholder="End Date"
                        type="daterange"
                        placeholder="Login Account"
                        :clearable="false"
                        @change="getRangeData"
                    />
                </el-form-item>
            </el-form>
        </Header>

        <div class="flex-1 bg-white p-20px grid grid-cols-3 gap-20px grid-rows-4" v-loading="loading">
            <Data1 :xData="state.xData" :yData="state.ax" name="ax" />
            <Data1 :xData="state.xData" :yData="state.ay" name="ay" />
            <Data1 :xData="state.xData" :yData="state.az" name="az" />
            <Data1 :xData="state.xData" :yData="state.gx" name="gx" />
            <Data1 :xData="state.xData" :yData="state.gy" name="gy" />
            <Data1 :xData="state.xData" :yData="state.gz" name="gz" />
            <Data2 :xData="state.xData" :yData="state.T1" name="T1" />
            <Data2 :xData="state.xData" :yData="state.T2" name="T2" />
            <Data2 :xData="state.xData" :yData="state.T3" name="T3" />
            <Data2 :xData="state.xData" :yData="state.T4" name="T4" />
            <Data2 :xData="state.xData" :yData="state.T5" name="T5" />
        </div>
        <div class="fixed top-60px left-160px w-100vw h-100vh z-1000 flex justify-center items-center" v-if="state.xData.length === 0">
            <span class="text-20px text-gray-500">No Data</span>
        </div>
    </div>
</template>

<script setup>
import { reactive, onMounted, ref } from 'vue';
import { getRangeDataApi } from '@/service/api';
import Data1 from './components/Data1.vue';
import Data2 from './components/Data2.vue';
import dayjs from 'dayjs';

const loading = ref(false);
const state = reactive({
    dateRange: [],
    xData: [],
    ax: [],
    ay: [],
    az: [],
    gx: [],
    gy: [],
    gz: [],
    T1: [],
    T2: [],
    T3: [],
    T4: [],
    T5: [],
});

onMounted(() => {
    state.dateRange = [dayjs().subtract(1, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')];
    getRangeData(state.dateRange);
});

const getRangeData = e => {
    loading.value = true;
    getRangeDataApi({
        start_time: e[0] + ' 00:00:00',
        end_time: e[1] + ' 23:59:59',
    })
        .then(res => {
            loading.value = false;
            for (const key in state) {
                if (key !== 'dateRange') {
                    state[key] = [];
                }
            }
            res.forEach(item => {
                state.xData.push(item.raw_data.timestamp);
                state.ax.push(item.raw_data.ax);
                state.ay.push(item.raw_data.ay);
                state.az.push(item.raw_data.az);
                state.gx.push(item.raw_data.gx);
                state.gy.push(item.raw_data.gy);
                state.gz.push(item.raw_data.gz);
                state.T1.push(item.transformed_data.T1);
                state.T2.push(item.transformed_data.T2);
                state.T3.push(item.transformed_data.T3);
                state.T4.push(item.transformed_data.T4);
                state.T5.push(item.transformed_data.T5);
            });
        })
        .catch(err => {
            loading.value = false;
        });
};

defineExpose({});
</script>

<style lang="scss" scoped>
:deep(.el-form-item) {
    margin-bottom: 0;
    margin-right: 0;
}
:deep(.el-table__inner-wrapper:before) {
    background: none;
}
</style>
