import type { Metadata } from "next";
import Link from "next/link";
import { guides } from "@/lib/guides";

export const metadata: Metadata = {
  title: "网盘搜索与资料分享指南",
  description: "盘搜整理公开网盘资源搜索、分享链接安全与文件整理的实用指南。",
  alternates: { canonical: "/guides" },
};

export default function GuidesPage() {
  return <main className="detail-shell"><article className="detail-card"><h1>网盘搜索与资料分享指南</h1><p className="detail-description">面向公开、合法资料的搜索、核验与整理建议。</p>{guides.map((guide) => <section key={guide.slug}><h2><Link href={`/guides/${guide.slug}`}>{guide.title}</Link></h2><p>{guide.description}</p></section>)}</article></main>;
}
