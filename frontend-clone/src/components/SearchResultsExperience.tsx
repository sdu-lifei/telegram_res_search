"use client";

import { useEffect, useState } from "react";
import { ResultsSection } from "./ResultsSection";
import { SiteHeader } from "./SiteHeader";
import type { SearchResponse, SearchResult } from "@/types/search";

export function SearchResultsExperience({ initialKeyword }: { initialKeyword: string }) {
  const [keyword, setKeyword] = useState(initialKeyword);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(Boolean(initialKeyword));
  const [message, setMessage] = useState("正在聚合多个公开索引，请稍候。");
  const [light, setLight] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("pansou-theme") === "light";
    queueMicrotask(() => setLight(stored)); document.documentElement.classList.toggle("light", stored);
    if (initialKeyword) void search(initialKeyword);
  }, [initialKeyword]); // eslint-disable-line react-hooks/exhaustive-deps

  async function search(nextKeyword?: string, refresh = false, track = true) {
    const query = (nextKeyword ?? keyword).trim();
    if (!query) { window.location.assign("/"); return; }
    setKeyword(query); setLoading(true); setMessage("正在聚合多个公开索引，请稍候。");
    history.replaceState(null, "", `/search?kw=${encodeURIComponent(query)}`);
    try {
      const response = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kw: query, res: "all", refresh, track, cloud_types: ["quark"] }) });
      const data = await response.json() as SearchResponse;
      setResults(data.results ?? []); setMessage(data.message ?? "");
      if ((data.status === "searching" || data.status === "in_progress") && !(data.results?.length)) setTimeout(() => void search(query, false, false), 4000);
    } catch { setResults([]); setMessage("搜索服务暂时不可用，请稍后重试。"); } finally { setLoading(false); }
  }

  function toggleTheme() { const next = !light; setLight(next); document.documentElement.classList.toggle("light", next); localStorage.setItem("pansou-theme", next ? "light" : "dark"); }

  return <><SiteHeader keyword={keyword} light={light} onKeywordChange={setKeyword} onSearch={(value) => void search(value)} onToggleTheme={toggleTheme} /><main className="search-page-shell"><ResultsSection keyword={keyword} results={results} loading={loading} message={message} onRefresh={() => void search(keyword, true)} /></main></>;
}
