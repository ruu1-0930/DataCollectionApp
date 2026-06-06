import axios from 'axios';
import { ElMessage } from 'element-plus';
import { useAdminStore } from '@/stores/useAdminStore';
// const whiteNameList = ['/login', '/register']
import router from '@/router';
// 导出Request类，可以用来自定义传递配置来创建实例
export class Request {
    // axios 实例
    instance = null;
    // 基础配置，url和超时时间
    baseConfig = {
        // 判断是测试环境还是正式环境
        baseURL: import.meta.env.MODE === 'development' ? import.meta.env.VITE_BASE_URL : import.meta.env.VITE_BASE_URL_PRO,
        timeout: 120000,
    };

    constructor(config) {
        // 使用axios.create创建axios实例
        this.instance = axios.create(Object.assign(this.baseConfig, config));
        this.instance.interceptors.request.use(
            config => {
                const adminStore = useAdminStore();
                if (adminStore.token) {
                    config.headers.Authorization = `Bearer ${adminStore.token}`;
                }
                return config;
            },
            err => {
                // 请求错误，这里可以用全局提示框进行提示
                return Promise.reject(err);
            }
        );

        this.instance.interceptors.response.use(
            res => {
                const custom = res.config.params?.custom || res.config.custom;
                // 自定义相应
                if (custom && custom.back_direct) {
                    return res.data;
                }
                // 直接返回res，当然你也可以只返回res.data
                // 系统如果有自定义code也可以在这里处理
                const { data, code, msg } = res.data;
                if (![200].includes(code)) {
                    ElMessage.error(msg);
                    if (code === 401) {
                        const adminStore = useAdminStore();
                        adminStore.adminLogout();
                        router.push({
                            name: 'proxy-login',
                        });
                    }
                    return Promise.reject(msg);
                }
                return data;
            },
            err => {
                // 这里用来处理http常见错误，进行全局提示
                let message = '';
                switch (err.response.status) {
                    case 400:
                        message = '请求错误(400)';
                        break;
                    case 401:
                        message = '未授权，请重新登录(401)';
                        const adminStore = useAdminStore();
                        adminStore.adminLogout();
                        router.push({
                            name: 'proxy-login',
                        });
                        // 这里可以做清空storage并跳转到登录页的操作
                        break;
                    case 403:
                        message = '拒绝访问(403)';
                        break;
                    case 404:
                        message = '请求出错(404)';
                        break;
                    case 408:
                        message = '请求超时(408)';
                        break;
                    case 500:
                        message = '服务器错误(500)';
                        break;
                    case 501:
                        message = '服务未实现(501)';
                        break;
                    case 502:
                        message = '网络错误(502)';
                        break;
                    case 503:
                        message = '服务不可用(503)';
                        break;
                    case 504:
                        message = '网络超时(504)';
                        break;
                    case 505:
                        message = 'HTTP版本不受支持(505)';
                        break;
                    default:
                        message = `连接出错(${err.response.status})!`;
                }
                // 这里错误消息可以使用全局弹框展示出来
                // 比如element plus 可以使用 ElMessage
                ElMessage.error(message);
                // 这里是AxiosError类型，所以一般我们只reject我们需要的响应即可
                return Promise.reject(err.response);
            }
        );
    }

    // 定义请求方法
    request = config => {
        return this.instance.request(config);
    };

    get = (url, params, config) => {
        return this.instance({
            url,
            method: 'get',
            params,
            ...config,
        });
    };

    post = (url, data, config) => {
        return this.instance({
            url,
            method: 'post',
            data,
            ...config,
        });
    };

    put = (url, data, config) => {
        return this.instance({
            url,
            method: 'put',
            data,
            ...config,
        });
    };

    delete = (url, params, config) => {
        return this.instance({
            url,
            method: 'delete',
            params,
            ...config,
        });
    };
}

// 默认导出Request实例
export default new Request({});
