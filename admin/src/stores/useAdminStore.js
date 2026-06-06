import { defineStore } from 'pinia';
import { ref } from 'vue';
import { adminLoginApi, adminInfoApi } from '@/service/api';
export const useAdminStore = defineStore(
    'adminStore',
    () => {
        const token = ref('');
        const admin = ref(null);

        async function adminLogin(loginForm) {
            const data = await adminLoginApi(loginForm);
            token.value = data.token;
            admin.value = data;
            return data.token;
        }

        function adminLogout() {
            token.value = '';
            admin.value = '';
        }

        async function getAdmin() {
            admin.value = await adminInfoApi();
        }

        return {
            admin,
            token,
            adminLogin,
            adminLogout,
            getAdmin,
        };
    },
    {
        // 开启持久化
        persist: [
            {
                key: '__store_manager',
                storage: localStorage,
                paths: ['token', 'admin'],
                debug: false,
            },
        ],
    }
);
