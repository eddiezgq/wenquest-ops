import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

// `npm run dev` proxies the API to a hub on localhost:8100; the hub serves the built files in production.
// frappe-ui's plugin without its Frappe-backend parts: our data comes from the hub's API (ADR-0013).
export default defineConfig({
  plugins: [frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false }), vue()],
  server: { proxy: { '/api': 'http://localhost:8100', '/login': 'http://localhost:8100' } },
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false },
})
