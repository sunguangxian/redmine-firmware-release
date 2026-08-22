import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [ElementPlusResolver()] })],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true
      },
      // 原生登录表单 POST /login，需与 /api 一样转到 FastAPI，否则 Vite 直接 404，浏览器也不会提示保存密码
      '/login': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true
      }
    }
  }
})
