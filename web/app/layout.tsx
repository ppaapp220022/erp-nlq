import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ERP 자연어 질의",
  description: "Odoo 데이터를 한국어로 묻고, 권한 안의 결과만 받는다",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
