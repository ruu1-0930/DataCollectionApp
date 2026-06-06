import './assets/main.css';
import 'virtual:uno.css';
import 'animate.css';
import App from './App.vue';
import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import { setupStore } from '@/stores';
import router from './router';
import 'element-plus/es/components/message/style/css';
import 'element-plus/es/components/message-box/style/css';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import vPermission from './directive';
import ImageUpload from '@/components/image-upload/index.vue';
import BaseChart from '@/components/base-chart/index.vue';
import Header from '@/components/Header/index.vue';

function setupApp() {
    const app = createApp(App);
    setupStore(app);
    app.use(router);

    app.component('ImageUpload', ImageUpload);
    app.component('BaseChart', BaseChart);
    app.component('Header', Header);

    app.use(ElementPlus, {
        locale: zhCn,
    });

    app.directive('permission', vPermission);

    app.mount('#app');
}

setupApp();
