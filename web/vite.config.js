import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// `npm run dev` proxies the API to a hub on localhost:8100; the hub serves the built files in production.
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://localhost:8100', '/login': 'http://localhost:8100' } },
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false },
})
