<template>
    <div class="login-bg h-full w-full">
        <div class="max-w-460px px-16px w-50% bg-white h-304px min-w-380px box rounded-8px fixed left-50% top-50% translate-x--50% translate-y--50%">
            <div class="px-54px flex flex-col items-center gap-0px">
                <div class="text-20px font-bold pt-50px">账号登录</div>
                <el-input v-model="state.username" placeholder="请输入请输入账号" class="mt-40px mb-5px"></el-input>
                <el-button :loading="state.loading" @click="login" class="w-full mt-40px" type="primary" size="large">登录</el-button>
                <div class="mt-10px flex justify-end w-full">
                    <el-checkbox v-model="remenberPass" label="记住密码" size="large" />
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { reactive, onBeforeMount, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useAdminStore } from '@/stores/useAdminStore';
import { useRouter } from 'vue-router';

const remenberPass = ref(true);
const adminStore = useAdminStore();
const router = useRouter();
const state = reactive({
    username: '',
    password: '',
    loading: false,
});

onBeforeMount(() => {
    const userinfo = localStorage.getItem('userinfo');
    if (userinfo) {
        const user = JSON.parse(userinfo);
        state.username = user.username;
        state.password = user.password;
    }
    if (adminStore.token) {
        router.push({
            name: 'manager',
        });
    }
});

async function login() {
    state.loading = true;
    try {
        const token = await adminStore.adminLogin({
            identifier: state.username,
        });
        if (token) {
            if (remenberPass.value) {
                localStorage.setItem('userinfo', JSON.stringify(state));
            }
            state.loading = false;
            ElMessage.success('登录成功');
            router.push({
                name: 'manager',
            });
        }
    } catch (error) {
        state.loading = false;
    }
}
</script>

<style lang="scss" scoped>
.login-bg {
    background-image: url('../../assets/images/1720883087433.jpg');
    background-size: cover;
    background-position: center;
    .box {
        box-shadow: 0 2px 11px 1px #cbbdf075;
    }
}
</style>
