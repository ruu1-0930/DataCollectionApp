<template>
    <div class="p-5px w-full h-full overflow-hidden flex flex-col gap-5px">
        <Header />
        <div class="flex-1 bg-white p-20px flex flex-wrap gap-30px content-start">
            <div class="w-40%">
                <span class="block mb-5px">Email</span>
                <el-input v-model="form.email" placeholder="Please input" class="w-300px!"></el-input>
            </div>

            <div class="w-40%">
                <span class="block mb-5px">Gender</span>
                <el-select v-model="form.gender" placeholder="Please select" class="w-300px!">
                    <el-option label="Male" value="male" />
                    <el-option label="Female" value="female" />
                </el-select>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Age</span>
                <el-input v-model="form.age" placeholder="Please input" class="w-300px!"></el-input>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Address</span>
                <el-input v-model="form.address" placeholder="Please input" class="w-300px!"></el-input>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Emergency Email</span>
                <el-input v-model="form.emergency_email" placeholder="Please input" class="w-300px!"></el-input>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Emergency Phone</span>
                <el-input v-model="form.emergency_phone" placeholder="Please input" class="w-300px!"></el-input>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Device Name</span>
                <el-input readonly v-model="form.device_name" placeholder="Please input" class="w-300px!"></el-input>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Frequency</span>
                <el-select v-model="form.frequency" placeholder="Please select" class="w-300px!">
                    <el-option label="1HZ" value="Low" />
                    <el-option label="5HZ" value="Medium" />
                    <el-option label="10HZ" value="High" />
                </el-select>
            </div>
            <div class="w-40%">
                <span class="block mb-5px">Is Enabled</span>
                <el-switch v-model="form.is_enabled" class="w-300px!" />
            </div>

            <div class="w-100% text-right mt-100px">
                <el-button type="primary" @click="save">Save</el-button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, reactive, onActivated } from 'vue';
import { updateUserInfoApi, updateDeviceApi, getDeviceListApi } from '@/service/api';
import { useAdminStore } from '@/stores/useAdminStore';

const adminStore = useAdminStore();
const form = reactive({
    address: '',
    age: 30,
    email: '',
    emergency_email: '',
    emergency_phone: '',
    gender: '',
    device_name: '',
    is_enabled: false,
    frequency: '',
    device_id: '',
});

onActivated(() => {
    for (const key in form) {
        form[key] = adminStore.admin[key];
    }
    getDeviceListApi({}).then(res => {
        if (res.length > 0) {
            form.device_name = res[0].device_name;
            form.is_enabled = res[0].is_enabled;
            form.frequency = res[0].frequency;
            form.device_id = res[0].id;
        }
    });
});

async function save() {
    const data = await updateUserInfoApi(form);
    await updateDeviceApi(form.device_id, form);
    adminStore.admin = data;
    ElMessage.success('Update successfully');
}
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
