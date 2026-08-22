import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [ElementPlusResolver()] })],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.component.test.ts'],
  },
})
