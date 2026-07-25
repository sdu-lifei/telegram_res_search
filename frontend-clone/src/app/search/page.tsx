import type { Metadata } from "next";
import { SearchResultsExperience } from "@/components/SearchResultsExperience";

export async function generateMetadata({ searchParams }: { searchParams: Promise<{ kw?: string }> }): Promise<Metadata> {
  const { kw = "" } = await searchParams;
  return { title: kw ? `${kw} 网盘资源搜索 - 盘搜` : "网盘资源搜索 - 盘搜", description: kw ? `搜索 ${kw} 的夸克网盘公开资源。` : "搜索公开网盘资源。", robots: { index: false, follow: true } };
}

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ kw?: string }> }) {
  const { kw = "" } = await searchParams;
  return <SearchResultsExperience initialKeyword={kw} />;
}
