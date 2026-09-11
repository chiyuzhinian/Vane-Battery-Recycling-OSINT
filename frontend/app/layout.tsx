import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "退役电池回收 OSINT 面板",
  description: "世界地图 · 采集审核 · 反哺闭环",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
