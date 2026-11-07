import type { NextConfig } from "next";

// 화면은 API 두 개(/generate, /execute)와 사용자 목록만 안다. 같은 출처로 프록시해 CORS를 열지 않는다.
const api = process.env.NLQ_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default config;
