<template>
    <div class="p-5px w-full h-full overflow-hidden flex flex-col gap-5px">
        <Header>
            <!-- <el-button type="primary" @click="handleAdd">Add</el-button> -->
        </Header>

        <div id="table-warper" style="height: calc(100% - 60px)" class="bg-white p-15px">
            <el-table border stripe v-loading="state.loading" :data="state.tableData" :height="384" style="width: 100%">
                <el-table-column prop="sat_title" align="center" width="100" />
                <el-table-column label="Title" align="center">
                    <template #default="{ row }">
                        <el-input v-model="row.title" />
                    </template>
                </el-table-column>
                <el-table-column label="Description" align="center">
                    <template #default="{ row }">
                        <el-input v-model="row.description" />
                    </template>
                </el-table-column>
            </el-table>
            <div class="flex justify-end mt-20px">
                <el-button type="primary" size="small" @click="handleSubmit()">Save</el-button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { reactive, onActivated, onMounted } from 'vue';
import { queryWeeklyScheduleApi, addWeeklyScheduleApi } from '@/service/api';

const state = reactive({
    tabHeight: 300,
    loading: false,
    tableData: [
        {
            sat_title: 'Mon',
            sat_titles: 'monday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Tue',
            sat_titles: 'tuesday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Wed',
            sat_titles: 'wednesday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Thu',
            sat_titles: 'thursday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Fri',
            sat_titles: 'friday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Sat',
            sat_titles: 'saturday',
            title: '',
            description: '',
        },
        {
            sat_title: 'Sun',
            sat_titles: 'sunday',
            title: '',
            description: '',
        },
    ],
});

onMounted(() => {
    state.tabHeight = document.getElementById('table-warper').getBoundingClientRect().height - 50;
    window.addEventListener('resize', () => {
        state.tabHeight = document.getElementById('table-warper').getBoundingClientRect().height - 50;
    });
});

onActivated(() => {
    getList();
});

function getList() {
    state.loading = true;
    queryWeeklyScheduleApi({}).then(res => {
        const { days } = res;
        state.tableData.forEach(item => {
            item.title = days?.[item.sat_titles]?.title ?? '';
            item.description = days?.[item.sat_titles]?.description ?? '';
        });
        state.loading = false;
    });
}

async function handleSubmit() {
    const days = {};
    state.tableData.forEach(item => {
        days[item.sat_titles + '_title'] = item.title;
        days[item.sat_titles + '_description'] = item.description;
    });

    addWeeklyScheduleApi(days).then(res => {
        ElMessage.success('Update Success!');
        getList();
    });
}

defineExpose({ state });
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
