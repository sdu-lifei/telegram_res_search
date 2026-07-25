import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://panss.dpdns.org"),
  title: { default: "盘搜 - 公开网盘资源搜索", template: "%s | 盘搜" },
  description: "盘搜聚合公开索引，帮助你搜索并检查可用的夸克网盘资源。",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    siteName: "盘搜",
    title: "盘搜 - 公开网盘资源搜索",
    description: "搜索公开索引资源，打开前自动检查可用性。",
  },
  twitter: { card: "summary", title: "盘搜 - 公开网盘资源搜索", description: "搜索公开索引资源，打开前自动检查可用性。" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify({
            "@context": "https://schema.org",
            "@graph": [
              { "@type": "WebSite", name: "盘搜", url: "https://panss.dpdns.org/", inLanguage: "zh-CN", potentialAction: { "@type": "SearchAction", target: "https://panss.dpdns.org/search?kw={search_term_string}", "query-input": "required name=search_term_string" } },
              { "@type": "Organization", name: "盘搜", url: "https://panss.dpdns.org/" },
            ],
          }).replace(/</g, "\\u003c") }}
        />
        {children}
      </body>
    </html>
  );
}
