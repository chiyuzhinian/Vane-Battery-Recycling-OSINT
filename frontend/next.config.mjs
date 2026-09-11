/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 后端直连（不用 rewrites：避免与 Vane 的 3000 端口的代理规则互相干扰）
  env: {
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000",
  },
};

export default nextConfig;
