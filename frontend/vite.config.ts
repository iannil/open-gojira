import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 7149,
    proxy: {
      '/api': {
        target: 'http://localhost:7150',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/echarts') || id.includes('echarts-for-react')) {
            return 'echarts';
          }
          if (id.includes('node_modules/antd') || id.includes('@ant-design')) {
            return 'vendor';
          }
        },
      },
    },
  },
})
