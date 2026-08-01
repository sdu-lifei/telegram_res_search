"use client";

import { CheckCircle2, ExternalLink, LoaderCircle, RefreshCw, SearchX } from "lucide-react";
import Link from "next/link";
import type { SearchResult } from "@/types/search";
import { ShareActions } from "./ShareActions";

interface ResultsSectionProps { keyword: string; results: SearchResult[]; loading: boolean; message: string; onRefresh: () => void; }

export function ResultsSection({ keyword, results, loading, message, onRefresh }: ResultsSectionProps) {
  function openInNewTab(url: string) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function openResource(resourceId: number | undefined, fallback: string) {
    if (!resourceId) { openInNewTab(fallback); return; }
    try {
      const response = await fetch(`/api/resources/${resourceId}/open`, { method: "POST" });
      const data = await response.json();
      openInNewTab(data.url || `/r/${resourceId}`);
    } catch {
      openInNewTab(`/r/${resourceId}`);
    }
  }

  if (!keyword && !loading) return null;
  return <section className="results-section">
    <div className="results-toolbar"><div><span>搜索结果</span><strong>{keyword || "等待搜索"}</strong></div><button type="button" onClick={onRefresh} disabled={loading}><RefreshCw size={16} />刷新</button></div>
    {loading && <div className="state-panel"><LoaderCircle className="spin" size={28} /><h2>正在搜索「{keyword}」</h2><p>{message || "正在聚合多个公开索引，请稍候。"}</p><div className="loading-bar"><span /></div></div>}
    {!loading && results.length === 0 && <div className="state-panel"><SearchX size={30} /><h2>暂未找到「{keyword}」</h2><p>{message || "可以尝试完整名称、年份或清晰度。"}</p></div>}
    {!loading && results.length > 0 && <div className="result-grid">{results.map((result, index) => {
      const link = result.links.find((item) => item.type === "quark") ?? result.links[0];
      const invalid = link?.transfer_status === "failed";
      return <article className="result-card" key={`${result.title}-${index}`}>
        <div className="result-top"><span className="disk-badge">夸克</span><span className={invalid ? "availability invalid" : "availability"}><CheckCircle2 size={13} />{invalid ? "已失效" : "可用资源"}</span></div>
        <h2>{link?.resource_id ? <Link href={`/d/${link.resource_id}`}>{result.title}</Link> : result.title}</h2><p>{result.description || "公开索引资源，打开前将自动检查有效性。"}</p>
        <div className="result-meta"><span>{result.channel.replace(/^tg:/, "")}</span><span>{new Date(result.datetime).toLocaleDateString("zh-CN")}</span></div>
        <div className="result-actions"><button type="button" disabled={!link || invalid} onClick={() => link && openResource(link.resource_id, link.url)}><ExternalLink size={16} />检查并打开</button><ShareActions keyword={keyword} title={result.title} /></div>
      </article>;
    })}</div>}
  </section>;
}
