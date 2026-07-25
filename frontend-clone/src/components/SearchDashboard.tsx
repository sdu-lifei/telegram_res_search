"use client";

import { Activity, Database, Search, Sparkles } from "lucide-react";
import type { HomeData } from "@/types/search";

interface SearchDashboardProps {
  home: HomeData | null;
  onSearch: (keyword?: string) => void;
}

export function SearchDashboard(props: SearchDashboardProps) {
  return (
    <section className="search-dashboard" id="search">
      <div className="search-main">
        <div className="search-heading"><div><h1>盘搜网盘资源搜索引擎</h1><p><span>盘搜</span> 聚合公开资源索引，自动检查链接并优先展示可用结果。</p></div><span className="brand-chip"><Sparkles size={14} /> 盘搜</span></div>
        <div className="hot-row"><span>热门搜索</span><div className="hot-cloud">{props.home?.hot_terms.map((term) => <button type="button" key={term.keyword} onClick={() => props.onSearch(term.keyword)}><span>{term.keyword}</span><small>◉ {term.count.toLocaleString()}</small></button>)}</div></div>
      </div>
      <aside className="search-overview" aria-label="搜索概览">
        <h2>搜索概览</h2>
        <div className="overview-card"><span><Database size={16} /> 总资源数</span><strong>{props.home?.stats.resources.toLocaleString() ?? "--"}</strong><p>每小时更新一次。</p></div>
        <div className="overview-card"><span><Activity size={16} /> 今日新增资源</span><strong>{props.home?.stats.daily_new.toLocaleString() ?? "--"}</strong><p>今日入库的可用资源。</p></div>
        <div className="overview-card"><span><Search size={16} /> 累计搜索次数</span><strong>{props.home?.stats.searches.toLocaleString() ?? "--"}</strong><p>用户提交的搜索总次数。</p></div>
      </aside>
    </section>
  );
}
