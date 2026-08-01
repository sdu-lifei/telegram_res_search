import type { MetadataRoute } from "next";
import type { CatalogResource } from "@/types/search";
import { guides } from "@/lib/guides";

function lastModified(datetime?: string) {
  const date = datetime && new Date(datetime);
  return date && Number.isFinite(date.valueOf()) && date.getUTCFullYear() >= 2000 ? date : undefined;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = "https://panss.dpdns.org";
  const api = process.env.API_INTERNAL_BASE || "http://127.0.0.1:8888";
  let items: CatalogResource[] = [];
  try { const response = await fetch(`${api}/api/catalog?limit=500`, { next: { revalidate: 3600 } }); items = (await response.json()).items || []; } catch {}
  return [
    { url: base, changeFrequency: "daily", priority: 1 },
    { url: `${base}/about`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${base}/llms.txt`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/guides`, changeFrequency: "weekly", priority: 0.8 },
    ...guides.map((guide) => ({ url: `${base}/guides/${guide.slug}`, lastModified: new Date(guide.datePublished), changeFrequency: "monthly" as const, priority: 0.7 })),
    ...items.map((item) => ({ url: `${base}/d/${item.id}`, lastModified: lastModified(item.datetime), changeFrequency: "weekly" as const, priority: 0.7 })),
  ];
}
