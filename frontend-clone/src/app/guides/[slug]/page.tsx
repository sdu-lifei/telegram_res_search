import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getGuide, guides } from "@/lib/guides";

const base = "https://panss.dpdns.org";

export function generateStaticParams() { return guides.map(({ slug }) => ({ slug })); }

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const guide = getGuide((await params).slug);
  if (!guide) return { title: "指南不存在" };
  return { title: guide.title, description: guide.description, keywords: guide.keywords, alternates: { canonical: `/guides/${guide.slug}` }, openGraph: { title: guide.title, description: guide.description, type: "article", url: `${base}/guides/${guide.slug}` } };
}

export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const guide = getGuide((await params).slug);
  if (!guide) notFound();
  const jsonLd = { "@context": "https://schema.org", "@type": "Article", headline: guide.title, description: guide.description, datePublished: guide.datePublished, dateModified: guide.datePublished, inLanguage: "zh-CN", mainEntityOfPage: `${base}/guides/${guide.slug}`, author: { "@type": "Organization", name: "盘搜" }, publisher: { "@type": "Organization", name: "盘搜", url: base } };
  return <main className="detail-shell"><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} /><article className="detail-card"><Link className="back-link" href="/guides">返回指南</Link><h1>{guide.title}</h1><p className="detail-description">更新于 {guide.datePublished}</p>{guide.sections.map((section) => <section key={section.heading}><h2>{section.heading}</h2>{section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</section>)}<Link className="detail-open" href="/">搜索公开网盘资源</Link></article></main>;
}
