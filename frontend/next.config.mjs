/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 后端直连（不用 rewrites：避免与 Vane 的 3000 端口的代理规则互相干扰）
  //
  // ⚠️ 默认端口是 **8010，不是 8000**（2026-09-12 实测修正）：
  //    8000 已被另一个项目 `lithium-intel`（Docker 容器，映射 0.0.0.0:8000）占用。
  //    审核面板 API 曾绑 127.0.0.1:8000，与它重叠 —— 而 Windows 上 `localhost`
  //    优先解析成 `::1`，请求会落到 **lithium-intel** 上，
  //    现象是：接口全 404，`/openapi.json` 里是 `/api/v1/articles` 之类别人的路由。
  //    → 面板统一用 8010，避开这个坑。
  env: {
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8010",
  },
};

export default nextConfig;
