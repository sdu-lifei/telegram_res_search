"use client";

import { Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { ShareActions } from "./ShareActions";

interface SiteHeaderProps {
  keyword: string;
  light: boolean;
  onKeywordChange: (value: string) => void;
  onSearch: (keyword?: string) => void;
  onToggleTheme: () => void;
}

export function SiteHeader({ keyword, light, onKeywordChange, onSearch, onToggleTheme }: SiteHeaderProps) {
  return (
    <header className="site-header">
      <div className="header-glow" />
      <div className="header-inner">
        <Link className="brand" href="/" aria-label="盘搜首页"><span className="brand-mark">P</span><strong>盘搜</strong></Link>
        <form className="header-search" onSubmit={(event) => { event.preventDefault(); onSearch(new FormData(event.currentTarget).get("keyword")?.toString()); }}>
          <input name="keyword" value={keyword} onChange={(event) => onKeywordChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); onSearch(event.currentTarget.value); } }} placeholder="输入关键字进行搜索" aria-label="顶部搜索关键词" />
          <button type="submit" aria-label="顶部搜索"><Search size={19} /></button>
        </form>
        <nav className="header-nav" aria-label="辅助导航"><a href="#search">资源搜索</a><a href="#guide">使用说明</a></nav>
        <div className="header-actions"><ShareActions keyword={keyword} compact /><button className="theme-toggle" type="button" onClick={onToggleTheme} aria-label="切换日夜模式">{light ? <Moon size={17} /> : <Sun size={17} />}<span>{light ? "夜间" : "日间"}</span></button></div>
      </div>
    </header>
  );
}
