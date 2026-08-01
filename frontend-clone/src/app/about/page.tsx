import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "关于盘搜与资源搜索说明",
  description: "了解盘搜如何聚合公开网盘资源索引、检查分享链接，并获得更有效的搜索建议。",
  alternates: { canonical: "/about" },
};

const faq = [
  ["盘搜是什么？", "盘搜是公开网盘资源的搜索与索引工具。本站不上传、不存储文件内容，仅展示公开网页中可检索到的信息。"],
  ["怎样提高搜索成功率？", "优先使用完整名称；不确定时增加年份、演员、季数、语言或清晰度等限定词。"],
  ["为什么打开前会检查资源？", "公开分享链接可能会被取消或过期。检查步骤用于减少无效跳转，实际可用性以网盘服务页面为准。"],
];

export default function AboutPage() {
  const jsonLd = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faq.map(([name, text]) => ({ "@type": "Question", name, acceptedAnswer: { "@type": "Answer", text } })) };
  return <main className="detail-shell">
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
    <article className="detail-card">
      <h1>关于盘搜</h1>
      <p className="detail-description">盘搜帮助用户检索公开网盘资源信息，并在跳转前进行可用性检查。请遵守所在地法律法规及内容平台规则。</p>
      <h2>常见问题</h2>
      {faq.map(([question, answer]) => <section key={question}><h3>{question}</h3><p>{answer}</p></section>)}
    </article>
  </main>;
}
