import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
//
// dev 서버는 3000 포트에서 뜨고, `/api` 요청을 Django(127.0.0.1:8000)로 프록시한다.
// 이렇게 하면 브라우저 입장에서는 프론트와 API가 같은 오리진(localhost:3000)이 되어
// - 백엔드가 내려주는 JWT 쿠키(access_token/refresh_token)가 1st-party 쿠키로 저장되고
// - CORS/SameSite 문제 없이 credentials(쿠키)가 그대로 오간다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
