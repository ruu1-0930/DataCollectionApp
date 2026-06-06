import { useAdminStore } from '@/stores/useAdminStore';

export default {
    async mounted(el) {
        const adminStore = useAdminStore();
        const admin = adminStore.admin;
        if (admin.role !== 'super') {
            el.parentNode.removeChild(el);
        }
    },
};
