import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import AutoImport from 'unplugin-auto-import/vite';
import Components from 'unplugin-vue-components/vite';
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';
import vue from '@vitejs/plugin-vue';
import vueDevTools from 'vite-plugin-vue-devtools';
import UnoCSS from 'unocss/vite';

export default defineConfig(configEnv => {
    const viteEnv = loadEnv(configEnv.mode, process.cwd());
    console.log(configEnv.mode, viteEnv);

    return {
        base: '/',
        plugins: [
            vue(),
            UnoCSS(),
            vueDevTools(),
            AutoImport({
                resolvers: [ElementPlusResolver()],
            }),
            Components({
                resolvers: [ElementPlusResolver()],
            }),
        ],
        resolve: {
            alias: {
                '@': fileURLToPath(new URL('./src', import.meta.url)),
            },
        },
        server: {
            // 是否开启 https
            https: false,
            // 端口号
            port: 1315,
            // // 监听所有地址
            proxy: {
                '/api': {
                    target: 'https://api.sarcopenianus.com',
                    changeOrigin: true,
                    rewrite: path => path.replace(/^\/api/, ''),
                },
                '/file': {
                    target: 'https://api.sarcopenianus.com',
                    changeOrigin: true,
                    rewrite: path => path.replace(/^\/file/, ''),
                },
            },
        },
    };
});
