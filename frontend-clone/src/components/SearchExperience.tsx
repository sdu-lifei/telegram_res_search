"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RecommendationRail } from "./RecommendationRail";
import { SearchDashboard } from "./SearchDashboard";
import { SiteHeader } from "./SiteHeader";
import type { HomeData } from "@/types/search";

export function SearchExperience() {
  const [keyword, setKeyword] = useState("");
  const [light, setLight] = useState(false);
  const [home, setHome] = useState<HomeData | null>(null);

  // Initial URL search runs once; subsequent searches are event-driven.
  useEffect(() => {
    const stored = localStorage.getItem("pansou-theme") === "light";
    queueMicrotask(() => setLight(stored)); document.documentElement.classList.toggle("light", stored);
    const loadHome = () => fetch("/api/home").then((response) => response.ok ? response.json() : Promise.reject()).then((data: HomeData) => setHome(data)).catch(() => {});
    loadHome();
    const refresh = window.setInterval(loadHome, 60 * 60 * 1000);
    return () => window.clearInterval(refresh);
  }, []);

  function runSearch(nextKeyword?: string) {
    const query = (nextKeyword ?? keyword).trim(); if (!query) return;
    window.location.assign(`/search?kw=${encodeURIComponent(query)}`);
  }

  function toggleTheme() { const next = !light; setLight(next); document.documentElement.classList.toggle("light", next); localStorage.setItem("pansou-theme", next ? "light" : "dark"); }

  return <>
<SiteHeader keyword={keyword} light={light} onKeywordChange={setKeyword} onSearch={runSearch} onToggleTheme={toggleTheme} />
<main className="page-shell">
<SearchDashboard home={home} onSearch={runSearch} />
<RecommendationRail items={home?.recommendations ?? []} updatedAt={home?.recommendations_updated_at} onSelect={runSearch} /><section className="guide" id="guide">
<h2>更准确地找到资源</h2>
<div>
<article>
<strong>1</strong>
<h3>输入完整名称</h3>
<p>片名搭配年份、演员或 4K 等关键词。</p>
</article>
<article>
<strong>2</strong>
<h3>等待自动检查</h3>
<p>系统会聚合索引并去除重复结果。</p>
</article>
<article>
<strong>3</strong>
<h3>检查并打开</h3>
<p>打开前再次验证资源，减少失效链接。</p>
</article>
</div>
</section>
<section className="guide" aria-labelledby="faq-title">
<h2 id="faq-title">盘搜常见问题</h2>
<div>
<article><h3>盘搜提供什么服务？</h3><p>盘搜只聚合公开网页中可检索到的网盘索引信息，不托管文件内容。</p></article>
<article><h3>如何提高搜索准确率？</h3><p>使用完整名称，并补充年份、演员、季数或清晰度等信息。</p></article>
<article><h3>为什么需要检查资源？</h3><p>公开分享链接可能失效，打开前检查可减少无效跳转。</p></article>
</div>
</section>
</main>
<footer>声明：本站仅提供公开网盘资源索引，不上传、不存储任何资源内容。<Link href="/guides">使用指南</Link><Link href="/about">关于盘搜</Link></footer>
</>;
}
