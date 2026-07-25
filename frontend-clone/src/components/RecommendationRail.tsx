"use client";

import Image from "next/image";
import type { Recommendation } from "@/types/search";

export function RecommendationRail({ items, updatedAt, onSelect }: { items: Recommendation[]; updatedAt?: string; onSelect: (keyword: string) => void }) {
  const updated = updatedAt ? new Date(updatedAt) : null;
  const time = updated?.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  return <section className="recommendations"><div className="section-head"><span>◉</span><h2>百度热榜推荐 TOP10</h2>{time && <small>更新于 {time}</small>}</div><div className="rail"><div className="rail-track">{items.map((item) => <button className="poster-card" type="button" key={item.title} onClick={() => onSelect(item.keyword)}><Image src={item.image} alt={`${item.title}海报`} width={160} height={214} sizes="(max-width: 640px) 160px, 190px" loading="eager" unoptimized /><span className="heat">热度 {item.heat.toLocaleString()}</span><span className="poster-tag">{item.category} · {item.genre}</span><strong>{item.title}</strong><p>{item.description}</p></button>)}</div></div></section>;
}
