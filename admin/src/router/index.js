import { createRouter, createWebHashHistory } from 'vue-router';

const router = createRouter({
    history: createWebHashHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/proxy-login',
            name: 'proxy-login',
            component: () => import('@/views/login/proxy-login.vue'),
            meta: {
                title: '登录',
            },
        },
        {
            path: '/',
            name: 'manager',
            redirect: '/manager/dashboard',
            component: () => import('@/components/proxy-admin/index.vue'),
            children: [
                {
                    path: '/manager/dashboard',
                    name: 'manager-dashboard',
                    component: () => import('@/views/proxy-admin/dashboard/dashboard.vue'),
                    meta: {
                        title: '仪表盘',
                    },
                },
                {
                    path: '/manager/user',
                    name: 'manager-user',
                    component: () => import('@/views/proxy-admin/user/user.vue'),
                    meta: {
                        title: '用户',
                    },
                },
                {
                    path: '/manager/statistics',
                    name: 'manager-statistics',
                    component: () => import('@/views/proxy-admin/statistics/statistics.vue'),
                    meta: {
                        title: '统计',
                    },
                },
                {
                    path: '/manager/schedule',
                    name: 'manager-schedule',
                    component: () => import('@/views/proxy-admin/schedule/schedule.vue'),
                    meta: {
                        title: '排程',
                    },
                },
                {
                    path: '/manager/settings',
                    name: 'manager-settings',
                    component: () => import('@/views/proxy-admin/settings/settings.vue'),
                    meta: {
                        title: '设置',
                    },
                },

                // 新增三个页面 用户数据 设备数据  账号管理
                {
                    path: '/manager/user-data',
                    name: 'manager-user-data',
                    component: () => import('@/views/proxy-admin/user-data/user-data.vue'),
                    meta: {
                        title: '用户数据',
                    },
                },
                {
                    path: '/manager/device-data',
                    name: 'manager-device-data',
                    component: () => import('@/views/proxy-admin/device-data/device-data.vue'),
                    meta: {
                        title: '设备数据',
                    },
                },
                {
                    path: '/manager/account',
                    name: 'manager-account',
                    component: () => import('@/views/proxy-admin/account/account.vue'),
                    meta: {
                        title: '账号管理',
                    },
                },
            ],
        },
    ],
});

router.beforeEach((to, from, next) => {
    document.title = to.meta.title;

    next();
});

export default router;
