import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      // 把组件库单独拆成一个包，业务代码改动时用户不用重新下载它
      output: { manualChunks: { "element-plus": ["element-plus", "@element-plus/icons-vue"] } },
    },
  },
  server: {
    port: 3000,
    // 开发时所有接口请求转给网关（make deps 启动的 nginx），前端不直接访问 8001–8004
    proxy: {
      "/api": "http://localhost:8000",
      "/ops": "http://localhost:8000",
    },
  },
});
