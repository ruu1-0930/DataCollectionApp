<template>
    <div class="h-60px bg-#fff px-20px flex items-center justify-between">
        <div><slot /></div>
        <div class="flex items-center gap-10px">
            <span class="text-16px font-bold">{{ admin.name }}</span>
            <el-upload
                :headers="headers"
                ref="upload"
                :action="actions"
                accept="image/*"
                :limit="9"
                :show-file-list="false"
                :on-success="uploadSucess"
            >
                <img :src="admin.avatar ? prefix + admin.avatar : avatar" alt="Logout" class="w-40px h-40px object-fill rounded-50%" />
            </el-upload>
        </div>
    </div>
</template>

<script setup>
import { useAdminStore } from '@/stores/useAdminStore';
import { computed } from 'vue';
import avatar from '@/assets/logo.png';
import { updateUserInfoApi } from '@/service/api';

const adminStore = useAdminStore();
const headers = { Authorization: adminStore.token };
const actions = import.meta.env.MODE === 'development' ? import.meta.env.VITE_BASE_FILE_URL : import.meta.env.VITE_BASE_FILE_URL_PRO;
const prefix = import.meta.env.MODE === 'development' ? import.meta.env.VITE_BASE_URL : import.meta.env.VITE_BASE_URL_PRO;

const admin = computed(() => adminStore.admin);

function uploadSucess(res) {
    updateUserInfoApi({ avatar: res.data.avatar_url });
    ElMessage.success('Update successfully');
    adminStore.admin.avatar = res.data.avatar_url;
}
</script>
