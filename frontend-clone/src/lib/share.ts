export type SharePlatform = "wechat" | "x";

export function buildPublicSearchUrl(keyword = "") {
  const url = new URL(keyword ? "/search" : "/", window.location.origin);
  if (keyword) url.searchParams.set("kw", keyword);
  return url.toString();
}

export function buildShareText(keyword = "", title = "") {
  if (title) return `盘搜搜索结果：${title}${keyword ? `，查询：${keyword}` : ""}`;
  return "盘搜：网盘资源搜索工具";
}

export function buildShareUrl(url: string, text: string) {
  return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
}

export async function shareToWeChat(url: string, text: string) {
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title: "盘搜", text, url });
      return "shared" as const;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return "cancelled" as const;
    }
  }

  const content = `${text}\n${url}`;
  try {
    await navigator.clipboard.writeText(content);
    return "copied" as const;
  } catch {
    window.prompt("请复制以下内容，再分享到微信群：", content);
    return "prompted" as const;
  }
}
