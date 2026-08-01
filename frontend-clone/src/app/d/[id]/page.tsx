import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ExternalLink, HardDrive, ShieldCheck } from "lucide-react";
import type { CatalogResource } from "@/types/search";

const publicBase = "https://panss.dpdns.org";
const apiBase = process.env.API_INTERNAL_BASE || "http://127.0.0.1:8888";

async function getResource(id: string): Promise<CatalogResource | null> {
  try {
    const response = await fetch(`${apiBase}/api/catalog/${id}`, { next: { revalidate: 1800 } });
    return response.ok ? await response.json() as CatalogResource : null;
  } catch { return null; }
}

export async function generateStaticParams() {
  try {
    const response = await fetch(`${apiBase}/api/catalog?limit=200`);
    const data = await response.json() as { items: CatalogResource[] };
    return data.items.map((item) => ({ id: String(item.id) }));
  } catch { return []; }
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const resource = await getResource(id);
  if (!resource) return { title: "资源不存在 - 盘搜" };
  const description = (resource.description || `${resource.title} 网盘资源`).slice(0, 150);
  return {
    title: `${resource.title} - 夸克网盘资源`,
    description,
    alternates: { canonical: `${publicBase}/d/${id}` },
    openGraph: { title: resource.title, description, type: "article", url: `${publicBase}/d/${id}` },
  };
}

export default async function ResourceDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const resource = await getResource(id);
  if (!resource) return <main className="detail-shell"><h1>资源不存在或已失效</h1><Link href="/">返回首页</Link></main>;
  const jsonLd = { "@context": "https://schema.org", "@type": "CreativeWork", name: resource.title, description: resource.description, dateModified: resource.datetime, url: `${publicBase}/d/${id}` };
  return <main className="detail-shell">
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
    <Link className="back-link" href="/"><ArrowLeft size={17} />返回搜索</Link>
    <article className="detail-card"><div className="detail-badges"><span><HardDrive size={15} />夸克网盘</span><span><ShieldCheck size={15} />打开前自动检查</span></div><h1>{resource.title}</h1><p className="detail-description">{resource.description || "公开索引资源，点击下方按钮检查并打开。"}</p><dl><div><dt>关键词</dt><dd>{resource.keyword}</dd></div><div><dt>来源</dt><dd>{resource.source}</dd></div><div><dt>更新时间</dt><dd>{resource.datetime ? new Date(resource.datetime).toLocaleDateString("zh-CN") : "近期"}</dd></div></dl><a className="detail-open" href={resource.open_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={18} />检查并打开资源</a></article>
    <section className="detail-tips"><h2>搜索建议</h2><p>如果资源失效，可以返回首页搜索完整片名、年份、演员或清晰度，系统会继续查找其他公开索引。</p></section>
  </main>;
}
