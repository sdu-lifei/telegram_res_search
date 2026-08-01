"use client";

import { useState } from "react";
import { buildPublicSearchUrl, buildShareText, buildShareUrl, shareToWeChat, type SharePlatform } from "@/lib/share";

interface ShareActionsProps { keyword?: string; title?: string; compact?: boolean; }

export function ShareActions({ keyword = "", title = "", compact = false }: ShareActionsProps) {
  const [status, setStatus] = useState("");

  async function share(platform: SharePlatform) {
    const url = buildPublicSearchUrl(keyword.trim());
    const text = buildShareText(keyword.trim(), title);
    if (platform === "wechat") {
      const result = await shareToWeChat(url, text);
      setStatus(result === "shared" ? "已打开系统分享面板" : result === "copied" ? "已复制，请粘贴到微信群" : result === "prompted" ? "请复制提示框内容分享到微信群" : "");
      return;
    }
    window.open(buildShareUrl(url, text), "_blank", "noopener,noreferrer");
    setStatus("已打开 X");
  }

  return <div className={`share-actions${compact ? " compact" : ""}`} aria-label={title ? "分享搜索结果" : "分享盘搜"}>
    <button type="button" title="分享到微信" aria-label="分享到微信" onClick={() => void share("wechat")}>微信</button>
    <button type="button" title="分享到 X" aria-label="分享到 X" onClick={() => void share("x")}>X</button>
    {status && <span className="share-status" role="status" aria-live="polite">{status}</span>}
  </div>;
}
