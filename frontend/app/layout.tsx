import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniCart Agent - 购物决策助手",
  description: "多模态购物决策 Agent · V0",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
